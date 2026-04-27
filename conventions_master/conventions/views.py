import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.http import FileResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone

from .models import *
from .forms import *
from .services.pdf_signer import signer_document_pdf, apposer_3_tampons_libres

# ==========================================
# 1. AUTHENTIFICATION & REDIRECTIONS
# ==========================================

def redirection_racine(request):
    if request.user.is_authenticated:
        role_url_map = {
            'ETUDIANT': 'dashboard_etudiant',
            'DOCTORANT': 'dashboard_doctorant',
            'ENSEIGNANT': 'dashboard_enseignant',
            'COORDINATEUR': 'dashboard_coordinateur',
            'ADMINISTRATEUR': 'dashboard_administrateur',
            'VICE_DOYEN': 'dashboard_vice_doyen',
        }
        return redirect(role_url_map.get(request.user.role, '/admin/'))
    return redirect('login')

class CustomLoginView(LoginView):
    template_name = 'conventions/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        user = self.request.user
        role_path_map = {
            'ETUDIANT': '/dashboard/etudiant/',
            'DOCTORANT': '/dashboard/doctorant/',
            'ENSEIGNANT': '/dashboard/enseignant/',
            'COORDINATEUR': '/dashboard/coordinateur/',
            'ADMINISTRATEUR': '/dashboard/administrateur/',
            'VICE_DOYEN': '/dashboard/vice-doyen/',
        }
        return role_path_map.get(user.role, '/admin/')

# Décorateurs de rôle
def is_etudiant(user): return user.is_authenticated and user.role == 'ETUDIANT'
def is_doctorant(user): return user.is_authenticated and user.role == 'DOCTORANT'
def is_enseignant(user): return user.is_authenticated and user.role == 'ENSEIGNANT'
def is_coordinateur(user): return user.is_authenticated and user.role == 'COORDINATEUR'
def is_administrateur(user): return user.is_authenticated and user.role == 'ADMINISTRATEUR'
def is_vice_doyen(user): return user.is_authenticated and user.role == 'VICE_DOYEN'

# ==========================================
# 2. ESPACE ADMINISTRATEUR (CONVENTIONS & MOBILITÉS)
# ==========================================

@user_passes_test(is_administrateur, login_url='/login/')
def dashboard_administrateur(request):
    """Vue principale pour l'admin : gestion des conventions en attente (Statut 2)"""
    attente = Convention.objects.filter(statut=2).order_by('date_creation')
    validees = Convention.objects.filter(statut__gte=3).order_by('-date_mise_a_jour')
    return render(request, 'conventions/dashboard_administrateur.html', {
        'attente': attente, 
        'validees': validees
    })

@user_passes_test(is_administrateur, login_url='/login/')
def dashboard_mobilite(request):
    """Gestion et recherche des mobilités doctorales"""
    query = request.GET.get('search', '')
    voir_archives = request.GET.get('archives', '0') == '1'

    mobilites = Mobilite.objects.all().select_related('etudiant').order_by('-date_debut')

    if voir_archives:
        mobilites = mobilites.filter(etat=True)
    else:
        mobilites = mobilites.filter(etat=False)

    if query:
        mobilites = mobilites.filter(
            Q(doctorant__last_name__icontains=query) | 
            Q(doctorant__first_name__icontains=query)
        )
    return render(request, 'conventions/dashboard_mobilite.html', {
        'mobilites': mobilites,
        'voir_archives': voir_archives,
        'query': query
    })

@user_passes_test(is_administrateur)
def dashboard_admin_alertes(request):
    """Alerte sur les mobilités sans contrat ou terminées sans retour"""
    alertes_mobilite = ConventionMobilite.objects.filter(
        Q(contrat_signe__isnull=True) | Q(contrat_signe="") | Q(date_fin__lt=timezone.now().date())
    ).select_related('doctorant', 'type_convention')
    
    return render(request, 'conventions/admin_alertes.html', {
        'alertes_mobilite': alertes_mobilite,
        'total_alertes': alertes_mobilite.count()
    })

@user_passes_test(is_administrateur, login_url='/login/')
def valider_convention_administrateur(request, convention_id):
    """Étape critique : l'admin place les coordonnées des tampons et du QR Code"""
    convention = get_object_or_404(Convention, id=convention_id, statut=2)
    
    if request.method == 'POST':
        if request.POST.get('action') == 'refuser':
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Refus administratif.')
            convention.save()
            Notification.objects.create(utilisateur=convention.etudiant, message="Convention rejetée par l'administration.")
            return redirect('dashboard_administrateur')

        # Sauvegarde des positions pour le Vice-Doyen
        convention.qr_x = float(request.POST.get('x_qr', 40))
        convention.qr_y = float(request.POST.get('y_qr', 40))
        convention.qr_page = int(request.POST.get('page_qr', 1))
        
        # Préparation du PDF (apposition des tampons encadrant/coord)
        input_pdf = convention.document_pdf.path
        output_pdf = input_pdf.replace('.pdf', '_prepare.pdf')
        vice_doyen = CustomUser.objects.filter(role='VICE_DOYEN').first()
        
        # Dictionnaire des coordonnées pour le service PDF
        coords = {
            'encadrant': (float(request.POST.get('x_enc', 0)), float(request.POST.get('y_enc', 0)), int(request.POST.get('page_enc', 1))),
            'coordinateur': (float(request.POST.get('x_coo', 0)), float(request.POST.get('y_coo', 0)), int(request.POST.get('page_coo', 1))),
            'doyen': (float(request.POST.get('x_doy', 0)), float(request.POST.get('y_doy', 0)), int(request.POST.get('page_doy', 1))),
        }

        if apposer_3_tampons_libres(input_pdf, output_pdf, convention, vice_doyen, coords):
            convention.document_pdf.name = output_pdf.split('media/')[-1]
            convention.statut = 3 # Passe au Vice-Doyen
            convention.save()
            return redirect('dashboard_administrateur')

    return render(request, 'conventions/placer_3_signatures.html', {'convention': convention})

# ==========================================
# 3. AUTRES VUES (DOCTORANT, VICE-DOYEN, ETC.)
# ==========================================

@user_passes_test(is_doctorant, login_url='/login/')
def dashboard_doctorant(request):
    profile = get_object_or_404(StudentProfile, user=request.user)
    inscription = InscriptionDoctorat.objects.filter(student=profile, est_valide=True).order_by('-annee_universitaire').first()
    annee = inscription.numero_reinscription if inscription else 1
    
    return render(request, 'conventions/dashboard_doctorant.html', {
        'profile': profile,
        'formations_disponibles': Formation.objects.filter(annee_doctorat_cible=annee),
        'participations': ParticipationFormation.objects.filter(student=profile).select_related('formation'),
        'conventions': Convention.objects.filter(etudiant=request.user).order_by('-date_creation')
    })

@user_passes_test(is_vice_doyen, login_url='/login/')
def dashboard_vice_doyen(request):
    attente = Convention.objects.filter(statut=3)
    validees = Convention.objects.filter(statut=4)
    stats = StudentProfile.objects.values('filiere').annotate(total=Count('id'))
    
    return render(request, 'conventions/dashboard_vice_doyen.html', {
        'attente': attente, 'validees': validees,
        'noms_filieres': [s['filiere'] for s in stats],
        'comptes_filieres': [s['total'] for s in stats],
    })

@login_required
def telecharger_convention(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id)
    # Sécurité : Seul l'étudiant concerné ou l'admin peut télécharger
    if request.user.role == 'ETUDIANT' and convention.etudiant != request.user:
        return HttpResponseForbidden()
    
    filepath = convention.document_pdf.path
    if os.path.exists(filepath):
        return FileResponse(open(filepath, 'rb'), content_type='application/pdf')
    return HttpResponseForbidden("Fichier introuvable.")

# ==========================================
# 4. CONTEXT PROCESSOR
# ==========================================

def notifications_globales(request):
    if request.user.is_authenticated:
        notifs = Notification.objects.filter(utilisateur=request.user, est_lue=False).order_by('-date_creation')
        return {'nb_notifs': notifs.count(), 'notifs_non_lues': notifs[:5]}
    return {'nb_notifs': 0, 'notifs_non_lues': []}

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import CustomUser, StudentProfile, Convention, Filiere, Notification
from .forms import UserProfileForm, EntrepriseForm, ConventionForm

# --- Décorateurs (Rappels) ---
def is_etudiant(user): return user.is_authenticated and user.role == 'ETUDIANT'
def is_enseignant(user): return user.is_authenticated and user.role == 'ENSEIGNANT'
def is_coordinateur(user): return user.is_authenticated and user.role == 'COORDINATEUR'

# ==========================================
# 1. PROFIL UTILISATEUR (Global pour tous)
# ==========================================
@login_required
def profil_utilisateur(request):
    """Permet à tout utilisateur de modifier ses infos (email, mot de passe, signature)"""
    if request.method == 'POST':
        # UserProfileForm doit gérer CustomUser (et potentiellement les champs du StudentProfile)
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour avec succès.")
            return redirect('profil_utilisateur') # Adaptez le nom de l'URL si besoin
    else:
        form = UserProfileForm(instance=request.user)
        
    return render(request, 'conventions/profil.html', {'form': form})


# ==========================================
# 2. DASHBOARD ÉTUDIANT (Licence / Master)
# ==========================================
@user_passes_test(is_etudiant, login_url='/login/')
def dashboard_etudiant(request):
    """Affiche les conventions de l'étudiant et son profil de scolarité"""
    # Récupération du profil étudiant (filiere, type_etudiant)
    profile = get_object_or_404(StudentProfile, user=request.user)
    
    # Historique de ses conventions
    conventions = Convention.objects.filter(etudiant=request.user).order_by('-date_creation')
    
    return render(request, 'conventions/dashboard_etudiant.html', {
        'conventions': conventions,
        'profile': profile
    })


# ==========================================
# 3. CRÉATION DE CONVENTION (Étudiant & Doctorant)
# ==========================================
@login_required
def creer_convention(request):
    """Gère la création de l'entreprise ET de la convention simultanément"""
    # Sécurité : vérifier que l'utilisateur a bien un profil étudiant/doctorant
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, "Erreur : Profil étudiant introuvable. Contactez l'administration.")
        return redirect('redirection_racine')

    if request.method == 'POST':
        form_ent = EntrepriseForm(request.POST)
        form_conv = ConventionForm(request.POST, request.FILES)
        
        if form_ent.is_valid() and form_conv.is_valid():
            # 1. Sauvegarder l'entreprise d'abord
            entreprise = form_ent.save()
            
            # 2. Lier la convention sans la sauvegarder immédiatement
            convention = form_conv.save(commit=False)
            convention.entreprise = entreprise
            convention.etudiant = request.user
            
            # 3. Moteur de routage / Workflow
            if convention.enseignant:
                # S'il a choisi un encadrant, ça part chez l'enseignant (Statut 0)
                convention.statut = 0
                Notification.objects.create(
                    utilisateur=convention.enseignant, 
                    message=f"Nouvelle demande d'encadrement de {request.user.get_full_name()}",
                    lien="/dashboard/enseignant/"
                )
            else:
                # S'il n'y a pas d'encadrant, ça part direct au coordinateur (Statut 1)
                convention.statut = 1
                if convention.filiere and convention.filiere.coordinateur:
                    Notification.objects.create(
                        utilisateur=convention.filiere.coordinateur, 
                        message=f"Dossier sans encadrant à traiter ({request.user.last_name})",
                        lien="/dashboard/coordinateur/"
                    )
            
            # 4. Sauvegarde finale
            convention.save()
            messages.success(request, "Votre convention a été soumise avec succès.")
            
            # Redirection dynamique selon le rôle
            if request.user.role == 'DOCTORANT':
                return redirect('dashboard_doctorant')
            return redirect('dashboard_etudiant')
    else:
        form_ent = EntrepriseForm()
        form_conv = ConventionForm()
        
    return render(request, 'conventions/creer_convention.html', {
        'form_ent': form_ent, 
        'form_conv': form_conv,
        'profile': profile
    })


# ==========================================
# 4. DASHBOARD ENSEIGNANT (Encadrant)
# ==========================================
@user_passes_test(is_enseignant, login_url='/login/')
def dashboard_enseignant(request):
    """L'enseignant voit les dossiers qui le demandent explicitement comme encadrant (Statut 0)"""
    
    # Dossiers en attente de son approbation
    attente = Convention.objects.filter(enseignant=request.user, statut=0).order_by('date_creation')
    
    # Historique de ses dossiers validés ou rejetés
    validees = Convention.objects.filter(enseignant=request.user, statut__gte=1).order_by('-date_mise_a_jour')
    
    return render(request, 'conventions/dashboard_enseignant.html', {
        'attente': attente, 
        'validees': validees
    })


# ==========================================
# 5. DASHBOARD COORDINATEUR (Responsable Filière)
# ==========================================
@user_passes_test(is_coordinateur, login_url='/login/')
def dashboard_coordinateur(request):
    """Le coordinateur gère les dossiers validés par les enseignants ou sans encadrant (Statut 1)"""
    
    # 1. Trouver quelles filières ce coordinateur gère
    mes_filieres = Filiere.objects.filter(coordinateur=request.user)
    
    # 2. Récupérer les conventions associées à CES filières (Statut 1 = Attente Coordinateur)
    attente = Convention.objects.filter(statut=1, filiere__in=mes_filieres).order_by('date_creation')
    
    # 3. Historique des dossiers qu'il a envoyés à l'administration (Statut >= 2)
    validees = Convention.objects.filter(statut__gte=2, filiere__in=mes_filieres).order_by('-date_mise_a_jour')
    
    # 4. Liste de tous les enseignants (au cas où il doit assigner un encadrant de force)
    enseignants = CustomUser.objects.filter(role='ENSEIGNANT', is_active=True)
    
    return render(request, 'conventions/dashboard_coordinateur.html', {
        'attente': attente, 
        'validees': validees, 
        'enseignants': enseignants,
        'mes_filieres': mes_filieres
    })

import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.conf import settings

from .models import *
from .forms import *
from .services.pdf_signer import signer_document_pdf


# =========================================================
# 1. VALIDATION ENSEIGNANT (Statut 0 -> 1 ou -1)
# =========================================================
@user_passes_test(is_enseignant, login_url='/login/')
def valider_convention_enseignant(request, convention_id):
    """L'encadrant accepte ou refuse le dossier de l'étudiant."""
    convention = get_object_or_404(Convention, id=convention_id, enseignant=request.user, statut=0)
    
    if request.method == 'POST':
        if 'refuser' in request.POST:
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Aucun motif précisé.')
            convention.save()
            Notification.objects.create(
                utilisateur=convention.etudiant, 
                message=f"❌ Convention refusée par l'encadrant. Motif: {convention.motif_rejet}", 
                lien="/dashboard/etudiant/"
            )
            messages.error(request, "Dossier refusé et retourné à l'étudiant.")
        else:
            convention.statut = 1
            convention.motif_rejet = None
            convention.save()
            # Notification au coordinateur de la filière
            if convention.filiere and convention.filiere.coordinateur:
                Notification.objects.create(
                    utilisateur=convention.filiere.coordinateur, 
                    message=f"L'encadrant a validé la convention de {convention.etudiant.last_name}", 
                    lien="/dashboard/coordinateur/"
                )
            messages.success(request, "Dossier validé et transmis au coordinateur.")
            
    return redirect('dashboard_enseignant')


# =========================================================
# 2. VALIDATION COORDINATEUR (Statut 1 -> 2, 0 ou -1)
# =========================================================
@user_passes_test(is_coordinateur, login_url='/login/')
def valider_convention_coordinateur(request, convention_id):
    """Le coordinateur valide pour l'administration, refuse, ou assigne un encadrant."""
    convention = get_object_or_404(Convention, id=convention_id, statut=1)
    
    if request.method == 'POST':
        if 'refuser' in request.POST:
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Refus de la coordination.')
            convention.save()
            Notification.objects.create(
                utilisateur=convention.etudiant, 
                message=f"❌ Convention refusée par le coordinateur. Motif: {convention.motif_rejet}"
            )
            messages.error(request, "Le dossier a été refusé.")
            
        elif 'assigner_encadrant' in request.POST:
            # Rétrograde le dossier au statut 0 (Chez l'enseignant)
            prof_id = request.POST.get('nouvel_encadrant')
            if prof_id:
                prof = CustomUser.objects.get(id=prof_id)
                convention.enseignant = prof
                convention.statut = 0 
                convention.save()
                Notification.objects.create(
                    utilisateur=prof, 
                    message=f"Vous avez été assigné comme encadrant pour {convention.etudiant.last_name}"
                )
                messages.success(request, f"Dossier transféré au Pr. {prof.last_name} pour encadrement.")
                
        else: # Clic sur "Valider pour l'Administration"
            convention.statut = 2
            convention.save()
            # On notifie tous les administrateurs
            admins = CustomUser.objects.filter(role='ADMINISTRATEUR')
            for admin in admins:
                Notification.objects.create(
                    utilisateur=admin, 
                    message=f"Nouveau dossier validé par la coordination ({convention.etudiant.last_name})"
                )
            messages.success(request, "Dossier validé et transmis à l'administration centrale.")
            
    return redirect('dashboard_coordinateur')


# =========================================================
# 3. VALIDATION VICE-DOYEN (Statut 3 -> 4 ou -1)
# =========================================================
@user_passes_test(is_vice_doyen, login_url='/login/')
def valider_convention_vice_doyen(request, convention_id):
    """Le Vice-Doyen appose le sceau cryptographique final ou refuse."""
    convention = get_object_or_404(Convention, id=convention_id, statut=3)
    
    if request.method == 'POST':
        if 'refuser' in request.POST:
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Refus du décanat.')
            convention.save()
            Notification.objects.create(utilisateur=convention.etudiant, message="❌ Convention refusée par le Vice-Doyen.")
            messages.error(request, "Le dossier a été rejeté.")
            
        elif 'valider' in request.POST:
            # Récupération des coordonnées placées par l'Admin à l'étape 2
            x_auto = convention.qr_x if convention.qr_x else 40
            y_auto = convention.qr_y if convention.qr_y else 40
            page_auto = convention.qr_page if convention.qr_page else 1
            
            input_pdf = convention.document_pdf.path
            output_pdf = input_pdf.replace('.pdf', '_VALIDE_FINAL.pdf')
            p12_path = os.path.join(settings.BASE_DIR, 'keystore', 'signer.p12')
            url_verification = request.build_absolute_uri(f'/convention/{convention.id}/telecharger/')
            
            # Signature et scellé du document
            success = signer_document_pdf(
                input_pdf_path=input_pdf,
                output_pdf_path=output_pdf,
                p12_path=p12_path,
                p12_password='votre_mot_de_passe_certificat', # À sécuriser dans un .env
                reason="Validation finale et scellé du décanat",
                location="Vice-Décanat",
                signer_name=f"Vice-Doyen {request.user.last_name}",
                x_coord=x_auto,
                y_coord=y_auto,
                page_number=page_auto,
                qr_data=url_verification,
                image_signature_path=None 
            )
            
            if success:
                convention.document_pdf.name = output_pdf.split('media/')[-1]
                convention.statut = 4
                convention.save()
                Notification.objects.create(
                    utilisateur=convention.etudiant,
                    message="🎉 Félicitations ! Votre convention a été validée et scellée par le décanat.",
                    lien="/dashboard/etudiant/"
                )
                messages.success(request, "Le document a été scellé cryptographiquement avec succès.")
            else:
                messages.error(request, "Erreur technique lors de la signature cryptographique.")
                
    return redirect('dashboard_vice_doyen')


# =========================================================
# 4. GESTION DES MOBILITÉS (ADMINISTRATEUR)
# =========================================================

@user_passes_test(is_administrateur, login_url='/login/')
def admin_ajouter_mobilite(request):
    """Création d'une nouvelle mobilité doctorale par l'admin."""
    if request.method == 'POST':
        form = MobiliteForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "La mobilité a été enregistrée avec succès dans le système.")
            return redirect('dashboard_mobilite')
    else:
        form = MobiliteForm()
    
    return render(request, 'conventions/admin_ajouter_mobilite.html', {'form': form})


@user_passes_test(is_administrateur, login_url='/login/')
def modifier_mobilite(request, pk):
    """Mise à jour d'un dossier de mobilité existant."""
    mobilite = get_object_or_404(Mobilite, pk=pk)
    
    if request.method == 'POST':
        # On passe l'instance existante pour faire un UPDATE et non un INSERT
        form = MobiliteForm(request.POST, request.FILES, instance=mobilite)
        if form.is_valid():
            form.save()
            messages.success(request, f"La mobilité de {mobilite.etudiant.last_name} a été mise à jour.")
            return redirect('dashboard_mobilite')
    else:
        form = MobiliteForm(instance=mobilite)
        
    return render(request, 'conventions/modifier_mobilite.html', {
        'form': form,
        'mobilite': mobilite
    })


@user_passes_test(is_administrateur, login_url='/login/')
def archiver_mobilite(request, pk):
    """Bascule l'état d'archivage (actif/archivé) pour nettoyer le tableau de bord."""
    mobilite = get_object_or_404(Mobilite, pk=pk)
    
    # Inversion du booléen
    mobilite.etat = not mobilite.etat
    mobilite.save()
    
    status = "archivée" if mobilite.etat else "restaurée"
    messages.success(request, f"Le dossier de {mobilite.etudiant.last_name} a été {status}.")
    
    return redirect('dashboard_mobilite')


@user_passes_test(is_administrateur, login_url='/login/')
def supprimer_mobilite(request, pk):
    """Suppression définitive d'un dossier de mobilité (requiert POST pour la sécurité)."""
    mobilite = get_object_or_404(ConventionMobilite, pk=pk)
    
    if request.method == 'POST':
        nom_doctorant = mobilite.doctorant.last_name
        mobilite.delete()
        messages.success(request, f"La mobilité de {nom_doctorant} a été supprimée définitivement.")
        
    return redirect('dashboard_mobilite')