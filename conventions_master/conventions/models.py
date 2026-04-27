from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings



from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator



from django.db.models import Count, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import datetime

class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    # Correction : Relation directe avec la table Filiere
    filiere = models.ForeignKey(
        'Filiere', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Filière / Master"
    )
    coordinateur = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Profil de {self.user.username}"
# 2. Suivi des inscriptions Doctorants
class InscriptionDoctorat(models.Model):
    # On utilise user__role pour traverser la relation vers CustomUser
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE, 
        limit_choices_to={'user__role': 'DOCTORANT'} 
    )
    annee_universitaire = models.CharField(max_length=10) # ex: 2025/2026
    numero_reinscription = models.IntegerField(default=1) # 1 = Nouveau, 2 = 2ème année, etc.
    date_inscription = models.DateField(auto_now_add=True)
    est_valide = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'annee_universitaire') # Un seul dossier par an




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
    # <-- NOUVEAU CHAMP POUR L'IMAGE DE LA SIGNATURE (PNG)
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

# --- Ajustement du modèle Formation ---
class Formation(models.Model):
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    formateur = models.ForeignKey(
        'EnseignantProfile', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='formations_animees'
    )

    # Système de cases à cocher pour cibler plusieurs années
    cible_1ere_annee = models.BooleanField(default=True, verbose_name="1ère Année")
    cible_2eme_annee = models.BooleanField(default=False, verbose_name="2ème Année")
    cible_3eme_annee = models.BooleanField(default=False, verbose_name="3ème Année")
    cible_4eme_annee_plus = models.BooleanField(default=False, verbose_name="4ème année et +")

    obligatoire = models.BooleanField(default=False)

    def __str__(self):
        return self.titre

    @property
    def annees_cibles_display(self):
        """Retourne une chaîne propre pour l'affichage (ex: '1ère, 2ème')"""
        targets = []
        if self.cible_1ere_annee: targets.append("1ère")
        if self.cible_2eme_annee: targets.append("2ème")
        if self.cible_3eme_annee: targets.append("3ème")
        if self.cible_4eme_annee_plus: targets.append("4ème+")
        return ", ".join(targets)


class ParticipationFormation(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE)
    # Note par défaut (ex: 0 ou None en attendant l'évaluation)
    note = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(20)], 
        null=True, 
        blank=True,
        default=0.0 
    )
    presence = models.BooleanField(default=False) # Par défaut absent jusqu'à validation

    class Meta:
        unique_together = ('student', 'formation') # Évite les doublons


# --- Ajustement du modèle Filiere ---
class Filiere(models.Model):
    nom = models.CharField(max_length=200)
    # Le coordinateur est maintenant un profil enseignant
    coordinateur = models.ForeignKey(
        EnseignantProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='filieres_gerees'
    )


class Entreprise(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.TextField()
    representant = models.CharField(max_length=150, help_text="Nom du signataire côté entreprise")
    ice = models.CharField(max_length=50, blank=True, null=True, help_text="Identifiant Commun de l'Entreprise")
    
    def __str__(self):
        return self.nom

class Convention(models.Model):
    # Les fameuses 5 étapes de ton workflow
    STATUT_CHOICES = (
        (0, 'Initié (Formulaire rempli)'),
        (1, 'En attente d\'encadrement'),
        (2, 'En attente de coordination'),
        (3, 'En attente du décanat'),
        (4, 'Validé (Signé par le Vice-Doyen)'),
    )
    
    # Liaisons avec les utilisateurs et l'entreprise
    etudiant = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='conventions_etudiant', limit_choices_to={'role': 'ETUDIANT'})
    # NOUVEAU : Lien vers la filière (Obligatoire)
    filiere = models.ForeignKey(Filiere, on_delete=models.SET_NULL, null=True, verbose_name="Filière")
    
    # MODIFIÉ : L'enseignant devient optionnel (blank=True, null=True)
    enseignant = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='conventions_encadrees', verbose_name="Encadrant (Optionnel)")
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE)
    
    # Détails du stage
    sujet_stage = models.CharField(max_length=255)
    date_debut = models.DateField()
    date_fin = models.DateField()
    
    # Suivi et Document
    statut = models.IntegerField(choices=STATUT_CHOICES, default=0)
    document_pdf = models.FileField(upload_to='conventions_pdfs/', blank=True, null=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    
    # NOUVEAU : Sauvegarde de l'emplacement du QR Code
    qr_x = models.FloatField(null=True, blank=True)
    qr_y = models.FloatField(null=True, blank=True)
    qr_page = models.IntegerField(null=True, blank=True)
    motif_rejet = models.TextField(blank=True, null=True, verbose_name="Motif du refus")
    def __str__(self):
        return f"Convention: {self.etudiant.last_name} - {self.entreprise.nom}"
# Ajoute ce modèle à la fin de models.py
class Notification(models.Model):
    utilisateur = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True, null=True)
    est_lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notif pour {self.utilisateur.username} - {self.message}"

def annee_actuelle():
    return timezone.now().year
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
    # Ajoute cette ligne pour filtrer
    limit_choices_to={'role': 'DOCTORANT'} 
)
    
    # Nouvelle relation ici
    type_convention = models.ForeignKey(
        TypeMobilite, 
        on_delete=models.PROTECT, # Empêche de supprimer un type utilisé par une mobilité
        verbose_name="Type de Convention"
    )

    # Selon ton année actuelle
    laboratoire_accueil = models.CharField(max_length=255)
    ville_pays = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    contrat_signe = models.FileField(upload_to='mobilites/contrats/')
    date_creation = models.DateTimeField(auto_now_add=True)
    retour_valide = models.BooleanField(default=False, verbose_name="Retour validé par l'admin")
    est_archive = models.BooleanField(
        default=False, 
        verbose_name="Dossier Archivé"
    )

    def __str__(self):
        status = "[ARCHIVÉ]" if self.est_archive else "[ACTIF]"
        return f"{status} {self.doctorant.last_name}"
    @property
    def est_terminee_sans_retour(self):
        from django.utils import timezone
        # Vérifie si la date de fin est passée et que le document de retour est vide
        return self.date_fin < timezone.now().date() and not self.contrat_signe

    def __str__(self):
        return f"{self.doctorant.last_name} - {self.type_convention.nom}"
    
class Mobilite(models.Model):
    # 1. OPTIMISATION : Lier directement à l'utilisateur (plus cohérent avec tes autres modèles)
    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='mobilites',
        # Tu peux limiter aux rôles étudiants si besoin :
        # limit_choices_to={'role__in': ['MASTER', 'LICENCE', 'DOCTORANT']}
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
    
    # 2. CORRECTION : Renommer 'type' pour éviter les conflits avec le mot-clé Python
    type_mobilite = models.CharField(max_length=20, choices=TYPE_MOBILITE)
    
    # 3. BONUS : Ajout d'un champ pour uploader un rapport ou une attestation (optionnel)
    document_justificatif = models.FileField(
        upload_to='mobilites/justificatifs/', 
        blank=True, 
        null=True,
        verbose_name="Attestation / Rapport (PDF)"
    )

    etat = models.BooleanField(
        default=False, 
        verbose_name="Dossier traité / clôturé"
    )

    def __str__(self):
        return f"Mobilité {self.destination} - {self.etudiant.last_name}"



@receiver(post_save, sender=Formation)
def inscrire_etudiants_automatiquement(sender, instance, created, **kwargs):
    if created:
        # 1. Calculer l'année universitaire actuelle (ex: "2025/2026")
        now = datetime.now()
        current_year = now.year
        if now.month < 9:  # Avant septembre, on est encore sur l'année précédente
            annee_universitaire_actuelle = f"{current_year-1}/{current_year}"
        else:
            annee_universitaire_actuelle = f"{current_year}/{current_year+1}"

        # 2. Définir les niveaux cibles
        niveaux_cibles = []
        if instance.cible_1ere_annee: niveaux_cibles.append(1)
        if instance.cible_2eme_annee: niveaux_cibles.append(2)
        if instance.cible_3eme_annee: niveaux_cibles.append(3)
        if instance.cible_4eme_annee_plus: niveaux_cibles.extend(range(4, 11))

        # 3. Filtrer les étudiants qui :
        #    - Ont une inscription VALIDE pour l'année EN COURS
        #    - Dont le nombre TOTAL d'inscriptions correspond au niveau cible
        etudiants_actifs = StudentProfile.objects.annotate(
            total_inscriptions=Count(
                'inscriptiondoctorat', 
                filter=Q(inscriptiondoctorat__est_valide=True)
            ),
            inscrit_cette_annee=Count(
                'inscriptiondoctorat', 
                filter=Q(
                    inscriptiondoctorat__est_valide=True, 
                    inscriptiondoctorat__annee=annee_universitaire_actuelle
                )
            )
        ).filter(
            inscrit_cette_annee__gt=0, # Doit être inscrit cette année
            total_inscriptions__in=niveaux_cibles # Le niveau doit correspondre
        )

        # 4. Création des participations
        participations = [
            ParticipationFormation(
                student=etudiant,
                formation=instance,
                note=0.0
            )
            for etudiant in etudiants_actifs
        ]
        
        ParticipationFormation.objects.bulk_create(participations, ignore_conflicts=True)