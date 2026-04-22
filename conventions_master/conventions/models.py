from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings

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
    filiere = models.CharField(max_length=100, blank=True, null=True)
    PAI = models.CharField(max_length=100, blank=True, null=True)
    # <-- NOUVEAU CHAMP POUR L'IMAGE DE LA SIGNATURE (PNG)
    signature_image = models.ImageField(upload_to='signatures/', null=True, blank=True)

class Filiere(models.Model):
    nom = models.CharField(max_length=200, verbose_name="Nom de la filière / Master")
    coordinateur = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, limit_choices_to={'role': 'COORDINATEUR'}, related_name="filieres_coordonnees")

    def __str__(self):
        return self.nom
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