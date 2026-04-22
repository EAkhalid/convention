from django.contrib import admin
from django.contrib.auth import get_user_model
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Entreprise, Convention, Filiere, Convention

# Configuration de l'affichage des utilisateurs
class CustomUserAdmin(UserAdmin):
    # Les colonnes qui s'afficheront dans le tableau de bord
    list_display = ('username', 'last_name', 'first_name', 'role', 'filiere', 'is_active')
    # Les filtres sur le côté droit
    list_filter = ('role', 'filiere', 'is_staff', 'is_superuser')
    # Les champs de recherche
    search_fields = ('username', 'last_name', 'first_name')
    
    # Ajout du champ "role" et "filiere" dans le formulaire de modification
    fieldsets = UserAdmin.fieldsets + (
        ('Rôle et Filière (Convention Stage)', {'fields': ('role', 'filiere')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rôle et Filière', {'fields': ('role', 'filiere')}),
    )


# Configuration pour l'import/export des Filières
class FiliereResource(resources.ModelResource):
    class Meta:
        model = Filiere
        fields = ('id', 'nom', 'coordinateur__username') # Champs à inclure dans le CSV

@admin.register(Filiere)
class FiliereAdmin(ImportExportModelAdmin):
    resource_class = FiliereResource
    list_display = ('nom', 'coordinateur')
    search_fields = ('nom',)

# Configuration pour les Conventions
class ConventionResource(resources.ModelResource):
    class Meta:
        model = Convention

@admin.register(Convention)
class ConventionAdmin(ImportExportModelAdmin):
    resource_class = ConventionResource
    list_display = ('etudiant', 'filiere', 'enseignant', 'statut', 'date_creation')
    list_filter = ('statut', 'filiere')
    search_fields = ('etudiant__last_name', 'filiere__nom')
    
    # Organisation des champs dans l'édition manuelle
    fieldsets = (
        ('Informations Générales', {
            'fields': ('etudiant', 'filiere', 'enseignant', 'statut')
        }),
        ('Gestion du PDF & Signatures', {
            'fields': ('document_pdf', 'qr_x', 'qr_y', 'qr_page'),
            'classes': ('collapse',),
        }),
        ('Retours & Rejets', {
            'fields': ('motif_rejet',),
        }),
    )

from import_export import resources, fields
from django.contrib.auth.hashers import make_password
from .models import CustomUser

class CustomUserResource(resources.ModelResource):
    # Mapping exact des colonnes de ton CSV
    username = fields.Field(attribute='username', column_name='username')
    first_name = fields.Field(attribute='first_name', column_name='first_name')
    last_name = fields.Field(attribute='last_name', column_name='laste_name') # Mapping de 'laste_name'
    role = fields.Field(attribute='role', column_name='role')
    filiere = fields.Field(attribute='structure', column_name='filiere')
    password_field = fields.Field(attribute='password', column_name='MASSAR')

    class Meta:
        model = CustomUser
        import_id_fields = ('username',)
        # Colonnes présentes dans ton fichier 'inscrip doctorat2.csv'
        fields = ('username', 'first_name', 'last_name', 'role', 'filiere', 'password_field','PAI')
        exclude = ('id',)

    def before_save_instance(self, instance, *args, **kwargs):
        # Hachage du code MASSAR pour le mot de passe
        if instance.password:
            pwd = str(instance.password).strip().upper()
            if not pwd.startswith(('pbkdf2_sha256$', 'bcrypt$', 'argon2')):
                instance.password = make_password(pwd)
        
        # On force le username (Code Massar/CIN) en majuscules
        if instance.username:
            instance.username = str(instance.username).strip().upper()
            
        super().before_save_instance(instance, *args, **kwargs)
# Enregistrement dans l'interface d'administration
@admin.register(CustomUser)
class CustomUserAdmin(ImportExportModelAdmin):
    resource_class = CustomUserResource
    list_display = ('username', 'last_name', 'first_name', 'role', 'email')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'last_name', 'first_name')

# Enregistrement des modèles pour qu'ils apparaissent dans l'interface
admin.site.register(Entreprise)

