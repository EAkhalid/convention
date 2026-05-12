from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from datetime import datetime

# Import de tous les modèles proprement en une seule fois
from .models import (
    CustomUser, EnseignantProfile, Filiere, StudentProfile, InscriptionDoctorat,
    FormationDoctorale, SessionFormation, ParticipationFormation,
    Entreprise, Convention, TypeMobilite, ConventionMobilite, Mobilite, Notification
)

# =========================================================
# 1. RESSOURCE D'IMPORTATION (LE SYSTÈME "3-EN-1")
# =========================================================
class StudentImportResource(resources.ModelResource):
    class Meta:
        model = CustomUser
        import_id_fields = ('username',)
        fields = ('username', 'first_name', 'last_name')

    def before_import_row(self, row, **kwargs):
        """ Étape 1 : On nettoie juste le Username pour éviter les doublons """
        niveau_brut = str(row.get('niveau', '')).strip().upper()
        username_initial = str(row.get('username', '')).strip().upper()
        
        prefix = 'MA' if ("MASTER" in niveau_brut or niveau_brut == "MA") else 'DO'
        
        if username_initial and not username_initial.startswith(prefix):
            row['username'] = f"{prefix}{username_initial}"
        else:
            row['username'] = username_initial

    def before_save_instance(self, instance, row, **kwargs):
        """ Étape 2 : On force les valeurs directement dans l'instance avant sauvegarde """
        niveau_brut = str(row.get('niveau', '')).strip().upper()
        
        # 1. On force le Rôle
        if "MASTER" in niveau_brut or niveau_brut == "MA":
            instance.role = 'ETUDIANT'
        else:
            instance.role = 'DOCTORANT'
            
        # 2. On force le statut actif
        instance.is_active = True
        
        # 3. On force le mot de passe s'il n'en a pas
        if not instance.password:
            pass_val = str(row.get('MASSAR', instance.username)).strip()
            instance.set_password(pass_val) # set_password hache automatiquement le mot de passe

    def after_save_instance(self, instance, row, **kwargs):
        """ Étape 3 : Création du profil et de l'inscription """
        nom_filiere = str(row.get('filiere', '')).strip()
        cne_val = str(row.get('MASSAR', '')).strip() 
        pai_val = str(row.get('PAI', '')).strip()
        
        # 1. Gestion de la filière
        filiere_obj = None
        if nom_filiere:
            filiere_obj, _ = Filiere.objects.get_or_create(nom=nom_filiere)

        # 2. Création du profil
        profile, _ = StudentProfile.objects.update_or_create(
            user=instance,
            defaults={
                'filiere': filiere_obj,
                'CNE': cne_val if cne_val else None, 
                'PAI': pai_val if pai_val else None,
            }
        )

        # 3. Inscription administrative (Si c'est un doctorant)
        if instance.role == 'DOCTORANT':
            # A. Calcul de l'année universitaire ACTUELLE (ex: on est en 2026, donc 2025/2026)
            now = datetime.now()
            annee_actuelle = now.year if now.month >= 9 else now.year - 1
            annee_univ_str = f"{annee_actuelle}/{annee_actuelle + 1}"
            
            # B. Calcul de sa "nième" année d'inscription (ex: s'il est de 2023 et on est en 2026 = 4ème inscription)
            numero_insc = 1
            if pai_val and pai_val.isdigit():
                numero_insc = annee_actuelle - int(pai_val) + 1
                if numero_insc < 1: 
                    numero_insc = 1
            
            # C. Création de son dossier d'inscription pour CETTE ANNÉE
            InscriptionDoctorat.objects.get_or_create(
                student=profile,
                annee_universitaire=annee_univ_str,
                defaults={
                    'numero_reinscription': numero_insc,
                    'est_valide': True 
                }
            )


class StudentExportResource(resources.ModelResource):
    identifiant = fields.Field(attribute='user__username', column_name='Username/CIN')
    nom = fields.Field(attribute='user__last_name', column_name='Nom')
    prenom = fields.Field(attribute='user__first_name', column_name='Prénom')
    email = fields.Field(attribute='user__email', column_name='Email')
    role_systeme = fields.Field(attribute='user__role', column_name='Rôle')
    nom_filiere = fields.Field(attribute='filiere__nom', column_name='Filière/Master')

    class Meta:
        model = StudentProfile
        fields = ('identifiant', 'nom', 'prenom', 'email', 'role_systeme', 'nom_filiere')
        export_order = fields

# =========================================================
# 2. ACTIONS PERSONNALISÉES
# =========================================================

@admin.action(description="[DÉBUG] Inscrire les doctorants éligibles à cette session")
def forcer_inscriptions_etudiants(modeladmin, request, queryset):
    inscriptions_ajoutees = 0
    etudiants_trouves_total = 0

    for session in queryset: # queryset contient désormais des SessionFormation
        print("\n" + "="*50)
        print(f"🔍 DÉBUT DU DÉBUG POUR LA SESSION : {session.formation.titre} ({session.annee_universitaire})")
        
        # A. Récupérer l'année de base (ex: "2024/2025" -> 2024)
        annee_base = int(session.annee_universitaire.split('/')[0])
        annee_limite = annee_base - 3
        
        # B. On récupère la configuration du catalogue (Quelles années sont ciblées ?)
        catalogue = session.formation

        # C. Récupérer TOUS les doctorants ACTIFS pour l'année de la session
        # C'est la garantie absolue de ne pas inscrire des gens qui ont abandonné !
        inscriptions_valides = InscriptionDoctorat.objects.filter(
            annee_universitaire=session.annee_universitaire,
            est_valide=True
        ).select_related('student')
        
        etudiants_actifs = [insc.student for insc in inscriptions_valides]
        print(f"📊 Doctorants avec inscription administrative valide en {session.annee_universitaire} : {len(etudiants_actifs)}")
        
        etudiants_eligibles = []

        for etudiant in etudiants_actifs:
            pai_brut = str(etudiant.PAI).strip().replace('.0', '') if etudiant.PAI else ""
            
            if not pai_brut.isdigit():
                continue 
                
            pai_int = int(pai_brut)
            est_eligible = False

            # D. Vérification par rapport aux cases cochées dans le catalogue
            if catalogue.cible_1ere_annee and pai_int == annee_base: 
                est_eligible = True
                print(f"   ✅ ÉLIGIBLE : {etudiant.user.last_name} (1ère année)")
            elif catalogue.cible_2eme_annee and pai_int == (annee_base - 1): 
                est_eligible = True
                print(f"   ✅ ÉLIGIBLE : {etudiant.user.last_name} (2ème année)")
            elif catalogue.cible_3eme_annee and pai_int == (annee_base - 2): 
                est_eligible = True
                print(f"   ✅ ÉLIGIBLE : {etudiant.user.last_name} (3ème année)")
            elif catalogue.cible_4eme_annee_plus and pai_int <= annee_limite: 
                est_eligible = True
                print(f"   ✅ ÉLIGIBLE : {etudiant.user.last_name} (4ème année ou +)")

            if est_eligible:
                etudiants_eligibles.append(etudiant)
                etudiants_trouves_total += 1

        # E. Inscrire à la session
        participations = []
        for etudiant in etudiants_eligibles:
            if not ParticipationFormation.objects.filter(student=etudiant, session=session).exists():
                participations.append(
                    ParticipationFormation(student=etudiant, session=session, note=0.0)
                )
        
        # F. Sauvegarder
        if participations:
            ParticipationFormation.objects.bulk_create(participations, ignore_conflicts=True)
            inscriptions_ajoutees += len(participations)
            
        print("="*50 + "\n")

    if etudiants_trouves_total == 0:
        modeladmin.message_user(request, "Aucun étudiant éligible trouvé ou aucune inscription valide pour cette année.", level=messages.WARNING)
    else:
        modeladmin.message_user(request, f"Succès : {etudiants_trouves_total} éligible(s) trouvé(s) -> {inscriptions_ajoutees} inscription(s) ajoutée(s).", level=messages.SUCCESS)


# =========================================================
# 3. CONFIGURATION DES CLASSES ADMIN
# =========================================================

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin, ImportExportModelAdmin):
    resource_class = StudentImportResource
    list_display = ('username', 'last_name', 'first_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Informations LISAC', {'fields': ('role', 'signature_image')}),
    )

@admin.register(StudentProfile)
class StudentProfileAdmin(ImportExportModelAdmin):
    resource_class = StudentExportResource
    list_display = ('user', 'get_role', 'filiere', 'PAI')
    list_filter = ('user__role', 'filiere')

    def get_role(self, obj):
        return obj.user.role
    get_role.short_description = 'Rôle'

# --- Formations (Nouvelle Architecture) ---

@admin.register(FormationDoctorale)
class FormationDoctoraleAdmin(admin.ModelAdmin):
    list_display = ('titre', 'obligatoire')
    list_filter = ('obligatoire',)
    search_fields = ('titre',)

@admin.register(SessionFormation)
class SessionFormationAdmin(admin.ModelAdmin):
    list_display = ('formation', 'annee_universitaire', 'formateur')
    list_filter = ('annee_universitaire', 'formation')
    search_fields = ('formation__titre',)
    # On attache notre action de débug ici, sur les sessions !
    actions = [forcer_inscriptions_etudiants]

@admin.register(ParticipationFormation)
class ParticipationFormationAdmin(admin.ModelAdmin):
    list_display = ('student', 'session', 'note', 'presence', 'est_validee')
    list_filter = ('session__annee_universitaire', 'session__formation', 'presence')
    search_fields = ('student__user__last_name', 'student__user__username')

# --- Conventions & Mobilités ---

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

@admin.register(EnseignantProfile)
class EnseignantProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'departement', 'specialite')
    search_fields = ('user__last_name', 'user__first_name', 'departement')

# Enregistrements simples
admin.site.register(InscriptionDoctorat)
admin.site.register(Filiere)
admin.site.register(Entreprise)
admin.site.register(Notification)
admin.site.register(TypeMobilite)
admin.site.register(Mobilite)