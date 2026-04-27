from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin

from .models import *

# =========================================================
# 1. RESSOURCE D'IMPORTATION (LE SYSTÈME "3-EN-1")
# =========================================================
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from .models import CustomUser, StudentProfile, InscriptionDoctorat
from import_export import resources, fields
from django.contrib.auth.hashers import make_password
from .models import CustomUser, StudentProfile

from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import CustomUser, StudentProfile, Filiere

from django.contrib.auth.hashers import make_password
from import_export import resources, fields
from .models import CustomUser, StudentProfile, Filiere

class StudentImportResource(resources.ModelResource):
    class Meta:
        model = CustomUser
        import_id_fields = ('username',)
        # On définit les colonnes que Django doit lire dans le fichier
        fields = ('username', 'first_name', 'last_name', 'email')

    def before_import_row(self, row, **kwargs):
        """
        Préparation des données avant la création de l'utilisateur.
        """
        niveau_brut = str(row.get('niveau', '')).strip().upper()
        username_initial = str(row.get('username', '')).strip().upper()
        
        # 1. LOGIQUE DES RÔLES ET PRÉFIXES
        # Si c'est un Master -> Role: ETUDIANT, Préfixe: MA
        if "MASTER" in niveau_brut or niveau_brut == "MA":
            row['role'] = 'ETUDIANT'
            prefix = 'MA'
        # Sinon (Doctorat) -> Role: DOCTORANT, Préfixe: DO
        else:
            row['role'] = 'DOCTORANT'
            prefix = 'DO'
        
        # 2. Application du préfixe au username
        if username_initial and not username_initial.startswith(prefix):
            row['username'] = f"{prefix}{username_initial}"
        else:
            row['username'] = username_initial

        # 3. Sécurité et Statut
        row['is_active'] = True
        
        # Mot de passe : On utilise le code MASSAR du Excel s'il existe, sinon le Username
        pass_val = str(row.get('MASSAR', row['username'])).strip()
        row['password'] = make_password(pass_val)

    def after_save_instance(self, instance, row, **kwargs):
        """
        Création du profil et liaison avec la table Filiere.
        """
        nom_filiere = str(row.get('filiere', '')).strip()
        
        # 1. Gestion de la relation ForeignKey avec la table Filiere
        filiere_obj = None
        if nom_filiere:
            # On cherche la filière par son nom, ou on la crée si elle n'existe pas
            filiere_obj, created = Filiere.objects.get_or_create(nom=nom_filiere)

        # 2. Mise à jour ou création du profil étudiant
        StudentProfile.objects.update_or_create(
            user=instance,
            defaults={
                'filiere': filiere_obj,
            }
        )




class StudentExportResource(resources.ModelResource):
    # Mapping des champs de l'utilisateur (Identity)
    identifiant = fields.Field(attribute='user__username', column_name='Username/CIN')
    nom = fields.Field(attribute='user__last_name', column_name='Nom')
    prenom = fields.Field(attribute='user__first_name', column_name='Prénom')
    email = fields.Field(attribute='user__email', column_name='Email')
    role_systeme = fields.Field(attribute='user__role', column_name='Rôle')
    
    # Mapping de la relation ForeignKey (Academic)
    nom_filiere = fields.Field(attribute='filiere__nom', column_name='Filière/Master')

    class Meta:
        model = StudentProfile
        # Définition de l'ordre des colonnes dans le fichier Excel
        fields = ('identifiant', 'nom', 'prenom', 'email', 'role_systeme', 'nom_filiere')
        export_order = fields

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin





@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ImportExportModelAdmin):
    resource_class = StudentImportResource
    list_display = ('username', 'last_name', 'first_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    
    fieldsets = UserAdmin.fieldsets + (
        ('Informations LISAC', {'fields': ('role', 'signature_image')}),
    )
# =========================================================
# 2. CONFIGURATION DES CLASSES ADMIN
# =========================================================


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'entreprise', 'filiere', 'statut', 'date_creation')
    list_filter = ('statut', 'filiere')
    search_fields = ('etudiant__last_name', 'entreprise__nom', 'sujet_stage')
    date_hierarchy = 'date_creation'

@admin.register(ConventionMobilite)
class ConventionMobiliteAdmin(admin.ModelAdmin):
    list_display = ('doctorant', 'type_convention', 'ville_pays', 'date_debut', 'retour_valide', 'est_archive')
    list_filter = ('retour_valide', 'est_archive', 'type_convention')
    search_fields = ('doctorant__last_name', 'laboratoire_accueil', 'ville_pays')

@admin.register(Formation)
class FormationAdmin(admin.ModelAdmin):
    # On affiche les nouvelles cibles dans la liste
    list_display = (
        'titre', 
        'formateur', 
        'cible_1ere_annee', 
        'cible_2eme_annee', 
        'cible_3eme_annee', 
        'cible_4eme_annee_plus', 
        'obligatoire'
    )
    
    # On permet de filtrer par année cible et par formateur
    list_filter = (
        'obligatoire',
        'formateur',
        'cible_1ere_annee', 
        'cible_2eme_annee', 
        'cible_3eme_annee', 
        'cible_4eme_annee_plus',
    )
    
    search_fields = ('titre', 'description', 'formateur__user__last_name')

@admin.register(ParticipationFormation)
class ParticipationFormationAdmin(admin.ModelAdmin):
    list_display = ('student', 'formation', 'note', 'presence')
    list_filter = ('formation', 'presence')

@admin.register(StudentProfile)
class StudentProfileAdmin(ImportExportModelAdmin):
    resource_class = StudentExportResource
    list_display = ('user', 'get_role', 'filiere')
    list_filter = ('user__role', 'filiere')

    # Petite méthode pour afficher le rôle dans la liste admin
    def get_role(self, obj):
        return obj.user.role
    get_role.short_description = 'Rôle'
# =========================================================
# 3. ENREGISTREMENTS SIMPLES
# =========================================================

@admin.register(EnseignantProfile)
class EnseignantProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'departement', 'specialite')
    search_fields = ('user__last_name', 'user__first_name', 'departement')


admin.site.register(InscriptionDoctorat)
admin.site.register(Filiere)
admin.site.register(Entreprise)
admin.site.register(Notification)
admin.site.register(TypeMobilite)
admin.site.register(Mobilite)