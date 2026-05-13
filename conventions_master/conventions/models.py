from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models import Count, Q
from datetime import datetime
from django.db.models.signals import post_save
from django.dispatch import receiver
# ==========================================
# UTILISATEURS ET PROFILS
# ==========================================

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('ETUDIANT', 'Étudiant'),
        ('ENSEIGNANT', 'Enseignant'),
        ('COORDINATEUR', 'Coordinateur'),
        ('ADMINISTRATEUR', 'Administrateur'), 
        ('VICE_DOYEN', 'Vice-Doyen'),
        ('DOCTORANT', 'Doctorant'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    signature_image = models.ImageField(upload_to='signatures/', null=True, blank=True)

class EnseignantProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='enseignant_profile'
    )
    departement = models.CharField(max_length=100, blank=True, null=True)
    specialite = models.CharField(max_length=150, blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"Pr. {self.user.last_name}"

class Filiere(models.Model):
    nom = models.CharField(max_length=200)
    coordinateur = models.ForeignKey(
        EnseignantProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='filieres_gerees'
    )
    
    def __str__(self):
        return self.nom

class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    filiere = models.ForeignKey(
        Filiere, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Filière / Master"
    )
    coordinateur = models.CharField(max_length=255, blank=True, null=True)
    
    PAI = models.CharField(
        max_length=4, 
        blank=True, 
        null=True, 
        verbose_name="Première Année d'Inscription (PAI)",
        help_text="Exemple : 2024"
    )
    CNE = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNE")

    def __str__(self):
        return f"Profil de {self.user.username}"

class InscriptionDoctorat(models.Model):
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE, 
        limit_choices_to={'user__role': 'DOCTORANT'} 
    )
    annee_universitaire = models.CharField(max_length=10) # ex: 2025/2026
    numero_reinscription = models.IntegerField(default=1) 
    date_inscription = models.DateField(auto_now_add=True)
    est_valide = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'annee_universitaire')
        
    def __str__(self):
        return f"{self.student.user.last_name} - {self.annee_universitaire}"

# ==========================================
# GESTION DES FORMATIONS (NOUVELLE ARCHITECTURE)
# ==========================================

class FormationDoctorale(models.Model):
    titre = models.CharField(max_length=255, unique=True, verbose_name="Titre de la formation")
    description = models.TextField(blank=True)
    credits = models.PositiveIntegerField(
        default=0, 
        verbose_name="Nombre de Crédits (ECTS)"
    )
    volume_horaire = models.PositiveIntegerField(
        default=0, 
        verbose_name="Volume Horaire (VH) en heures"
    )
    cible_1ere_annee = models.BooleanField(default=True, verbose_name="1ère Année")
    cible_2eme_annee = models.BooleanField(default=False, verbose_name="2ème Année")
    cible_3eme_annee = models.BooleanField(default=False, verbose_name="3ème Année")
    cible_4eme_annee_plus = models.BooleanField(default=False, verbose_name="4ème année et +")

    obligatoire = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Formation Doctorale (Catalogue)"
        verbose_name_plural = "Formations Doctorales"

    def __str__(self):
        return self.titre


# ==========================================
class SessionFormation(models.Model):
    formation = models.ForeignKey(
        'FormationDoctorale', 
        on_delete=models.CASCADE, 
        related_name='sessions',
        verbose_name="Formation liée"
    )
    annee_universitaire = models.CharField(
        max_length=9, 
        verbose_name="Année universitaire",
        help_text="Exemple: 2024/2025"
    )
    formateur = models.ForeignKey(
        'EnseignantProfile', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='sessions_animees'
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('formation', 'annee_universitaire')
        verbose_name = "Session de Formation"
        verbose_name_plural = "Sessions de Formation"

    def __str__(self):
        return f"{self.formation.titre} - {self.annee_universitaire}"

    def save(self, *args, **kwargs):
        # 1. On sauvegarde d'abord la session normalement
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # 2. Si c'est une nouvelle session, on lance les inscriptions
        if is_new:
            self.generer_inscriptions_automatiques()
    def generer_inscriptions_automatiques(self):
        from .models import ParticipationFormation, InscriptionDoctorat, SessionFormation
        from django.db.models import Q

        # =========================================================
        # 1. RÉCUPÉRATION DE L'ANNÉE DE LA SESSION ACTUELLE
        # =========================================================
        try:
            valeur_saisie = str(self.annee_universitaire).strip()
            if '/' in valeur_saisie:
                annee_fin = int(valeur_saisie.split('/')[1])
            else:
                annee_fin = int(valeur_saisie) + 1 
            
            if annee_fin < 100: annee_fin += 2000
        except Exception:
            return

        annee_debut = str(annee_fin - 1)
        annee_debut_courte = annee_debut[2:]

        inscriptions_actives = InscriptionDoctorat.objects.filter(
            Q(annee_universitaire__startswith=annee_debut) | 
            Q(annee_universitaire__startswith=annee_debut_courte),
            est_valide=True
        ).select_related('student', 'student__user')

        catalogue = self.formation
        participations_a_creer = []

        # =========================================================
        # 2. DÉTECTION AUTOMATIQUE DE L'ANNÉE DE LANCEMENT (NOUVEAU)
        # =========================================================
        # On cherche toutes les sessions historiques de ce module
        sessions_historiques = SessionFormation.objects.filter(formation=catalogue)
        annees_debut_historiques = []
        
        for s in sessions_historiques:
            try:
                s_annee = str(s.annee_universitaire).strip()
                if '/' in s_annee:
                    a_deb = int(s_annee.split('/')[0])  # Ex: "2023" pour "2023/2024"
                else:
                    a_deb = int(s_annee)
                if a_deb < 100: a_deb += 2000
                annees_debut_historiques.append(a_deb)
            except:
                pass

        # L'année de lancement est la plus petite année trouvée !
        annee_lancement_module = min(annees_debut_historiques) if annees_debut_historiques else 0

        min_annee_cible = None
        if catalogue.cible_1ere_annee: min_annee_cible = 1
        elif catalogue.cible_2eme_annee: min_annee_cible = 2
        elif catalogue.cible_3eme_annee: min_annee_cible = 3
        elif catalogue.cible_4eme_annee_plus: min_annee_cible = 4

        # =========================================================
        # 3. BOUCLE D'ANALYSE ET D'INSCRIPTION
        # =========================================================
        for ins in inscriptions_actives:
            student = ins.student
            
            if student.user.is_superuser or student.id == 1:
                continue

            try:
                pai_int = int(float(str(student.PAI).strip()))
            except:
                continue
            
            annee_etude = annee_fin - pai_int
            if annee_etude < 1: 
                continue

            doit_passer_module = False

            # --- RÈGLE A : LE FLUX NORMAL ---
            if (catalogue.cible_1ere_annee and annee_etude == 1) or \
               (catalogue.cible_2eme_annee and annee_etude == 2) or \
               (catalogue.cible_3eme_annee and annee_etude == 3) or \
               (catalogue.cible_4eme_annee_plus and annee_etude >= 4):
                doit_passer_module = True

            # --- RÈGLE B : LE RATTRAPAGE & NON-RÉTROACTIVITÉ ---
            elif min_annee_cible and annee_etude > min_annee_cible:
                # La règle magique : le PAI doit être supérieur ou égal à l'année de lancement dynamique
                if pai_int >= annee_lancement_module:
                    doit_passer_module = True

            # --- RÈGLE C : VÉRIFICATION DE LA VALIDATION ---
            if doit_passer_module:
                deja_valide = ParticipationFormation.objects.filter(
                    student=student, session__formation=catalogue
                ).exclude(session=self).filter(Q(presence=True) | Q(note__gte=10.0)).exists()

                if not deja_valide:
                    participations_a_creer.append(ParticipationFormation(student=student, session=self, note=0.0))

        # =========================================================
        # 4. SAUVEGARDE EN BASE DE DONNÉES
        # =========================================================
        ParticipationFormation.objects.filter(session=self).delete()
        if participations_a_creer:
            ParticipationFormation.objects.bulk_create(participations_a_creer, ignore_conflicts=True)
class ParticipationFormation(models.Model):
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE,
        related_name='participations'
    )
    session = models.ForeignKey(
        SessionFormation, 
        on_delete=models.CASCADE,
        related_name='inscrits'
    )
    note = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(20)], 
        null=True, 
        blank=True,
        default=0.0 
    )
    presence = models.BooleanField(default=False, verbose_name="Présent / Validé")

    class Meta:
        unique_together = ('student', 'session')
        verbose_name = "Participation"
        verbose_name_plural = "Participations"

    def __str__(self):
        return f"{self.student.user.last_name} - {self.session}"

    @property
    def est_validee(self):
        if self.presence or (self.note is not None and self.note >= 10.0):
            return True
        return False

# ==========================================
# CONVENTIONS ET STAGES
# ==========================================

class Entreprise(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.TextField()
    representant = models.CharField(max_length=150, help_text="Nom du signataire côté entreprise")
    ice = models.CharField(max_length=50, blank=True, null=True, help_text="Identifiant Commun de l'Entreprise")
    
    def __str__(self):
        return self.nom

class Convention(models.Model):
    STATUT_CHOICES = (
        (0, 'Initié (Formulaire rempli)'),
        (1, 'En attente d\'encadrement'),
        (2, 'En attente de coordination'),
        (3, 'En attente du décanat'),
        (4, 'Validé (Signé par le Vice-Doyen)'),
    )
    
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conventions_etudiant', limit_choices_to={'role': 'ETUDIANT'})
    filiere = models.ForeignKey(Filiere, on_delete=models.SET_NULL, null=True, verbose_name="Filière")
    enseignant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='conventions_encadrees', verbose_name="Encadrant (Optionnel)")
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE)
    
    sujet_stage = models.CharField(max_length=255)
    date_debut = models.DateField()
    date_fin = models.DateField()
    
    statut = models.IntegerField(choices=STATUT_CHOICES, default=0)
    document_pdf = models.FileField(upload_to='conventions_pdfs/', blank=True, null=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    
    qr_x = models.FloatField(null=True, blank=True)
    qr_y = models.FloatField(null=True, blank=True)
    qr_page = models.IntegerField(null=True, blank=True)
    motif_rejet = models.TextField(blank=True, null=True, verbose_name="Motif du refus")
    
    def __str__(self):
        return f"Convention: {self.etudiant.last_name} - {self.entreprise.nom}"

# ==========================================
# MOBILITÉS
# ==========================================

class TypeMobilite(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Type de Mobilité")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Type de Mobilité"
        verbose_name_plural = "Types de Mobilité"

class ConventionMobilite(models.Model):
    doctorant = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='mobilites_doctorales',
        limit_choices_to={'role': 'DOCTORANT'} 
    )
    type_convention = models.ForeignKey(
        TypeMobilite, 
        on_delete=models.PROTECT,
        verbose_name="Type de Convention"
    )
    laboratoire_accueil = models.CharField(max_length=255)
    ville_pays = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    contrat_signe = models.FileField(upload_to='mobilites/contrats/')
    date_creation = models.DateTimeField(auto_now_add=True)
    retour_valide = models.BooleanField(default=False, verbose_name="Retour validé par l'admin")
    est_archive = models.BooleanField(default=False, verbose_name="Dossier Archivé")

    @property
    def est_terminee_sans_retour(self):
        return self.date_fin < timezone.now().date() and not self.contrat_signe

    def __str__(self):
        status = "[ARCHIVÉ]" if self.est_archive else "[ACTIF]"
        return f"{status} {self.doctorant.last_name} - {self.type_convention.nom}"
    
class Mobilite(models.Model):
    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='mobilites'
    )
    destination = models.CharField(max_length=255)
    etablissement_accueil = models.CharField(max_length=255)
    date_debut = models.DateField()
    date_fin = models.DateField()
 
    TYPE_MOBILITE = (
        ('STAGE', 'Stage de recherche'),
        ('COURS', 'Semestre d\'études'),
        ('CONFERENCE', 'Participation Conférence'),
    )
    
    type_mobilite = models.CharField(max_length=20, choices=TYPE_MOBILITE)
    document_justificatif = models.FileField(
        upload_to='mobilites/justificatifs/', 
        blank=True, 
        null=True,
        verbose_name="Attestation / Rapport (PDF)"
    )
    etat = models.BooleanField(default=False, verbose_name="Dossier traité / clôturé")

    def __str__(self):
        return f"Mobilité {self.destination} - {self.etudiant.last_name}"

# ==========================================
# NOTIFICATIONS
# ==========================================

class Notification(models.Model):
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True, null=True)
    est_lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notif pour {self.utilisateur.username} - {self.message}"

def annee_actuelle():
    return timezone.now().year

@receiver(post_save, sender=SessionFormation)
def inscription_automatique_phd(sender, instance, created, **kwargs):
    """
    Inscrit automatiquement les doctorants éligibles (nouveaux + rattrapages)
    lors de la création d'une nouvelle session.
    """
    if not created:
        return  # On n'agit que si c'est une création, pas une modification

    session = instance
    catalogue = session.formation
    
    # 1. Extraction de l'année de base (ex: "2025/2026" -> 2025)
    try:
        annee_base = int(session.annee_universitaire.split('/')[0])
    except (ValueError, IndexError):
        return # Format d'année invalide

    # 2. Récupérer les doctorants ayant une inscription VALIDE cette année
    inscriptions_actives = InscriptionDoctorat.objects.filter(
        annee_universitaire=session.annee_universitaire,
        est_valide=True
    ).select_related('student__user')

    participations_a_creer = []

    for inscription in inscriptions_actives:
        student = inscription.student
        pai_str = str(student.PAI).strip().replace('.0', '')
        
        if not pai_str.isdigit():
            continue
            
        pai_int = int(pai_str)
        est_concerne = False

        # --- A. VERIFICATION DU FLUX NORMAL (Cible PAI) ---
        if catalogue.cible_1ere_annee and pai_int == annee_base:
            est_concerne = True
        elif catalogue.cible_2eme_annee and pai_int == (annee_base - 1):
            est_concerne = True
        elif catalogue.cible_3eme_annee and pai_int == (annee_base - 2):
            est_concerne = True
        elif catalogue.cible_4eme_annee_plus and pai_int <= (annee_base - 3):
            est_concerne = True

        # --- B. VERIFICATION DU RATTRAPAGE (Dette) ---
        if not est_concerne:
            # On vérifie si l'étudiant a déjà validé une session de ce catalogue
            deja_valide = ParticipationFormation.objects.filter(
                student=student,
                session__formation=catalogue
            ).filter(Q(presence=True) | Q(note__gte=10.0)).exists()

            if not deja_valide:
                est_concerne = True

        # --- C. PREPARATION DE L'INSCRIPTION ---
        if est_concerne:
            participations_a_creer.append(
                ParticipationFormation(
                    student=student,
                    session=session,
                    note=0.0,
                    presence=False
                )
            )

    # 3. Création groupée en base de données (plus rapide)
    if participations_a_creer:
        ParticipationFormation.objects.bulk_create(participations_a_creer, ignore_conflicts=True)