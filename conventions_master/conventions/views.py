import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.http import FileResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib import messages
from django.db.models import Count

from .models import *
from .forms import *
from .services.pdf_signer import signer_document_pdf, apposer_3_tampons_libres
# ==========================================
# REDIRECTION DE LA PAGE D'ACCUEIL (RACINE /)
# ==========================================
def redirection_racine(request):
    """
    Aiguille l'utilisateur vers la page de connexion s'il n'est pas connecté,
    ou vers son tableau de bord respectif s'il l'est déjà.
    """
    if request.user.is_authenticated:
        if request.user.role == 'ETUDIANT': 
            return redirect('dashboard_etudiant')
        elif request.user.role == 'ENSEIGNANT': 
            return redirect('dashboard_enseignant')
        elif request.user.role == 'COORDINATEUR': 
            return redirect('dashboard_coordinateur')
        elif request.user.role == 'ADMINISTRATEUR': 
            return redirect('dashboard_administrateur')
        elif request.user.role == 'VICE_DOYEN': 
            return redirect('dashboard_vice_doyen')
        else:
            return redirect('/admin/')
    else:
        # S'il n'est pas connecté, on l'envoie sur la page de connexion
        return redirect('login')
# ==========================================
# AUTHENTIFICATION & RÔLES
# ==========================================
class CustomLoginView(LoginView):
    template_name = 'conventions/login.html'
    redirect_authenticated_user = True 
    
    # NOUVEAU : Le "vigile" qui force la redirection si on est déjà connecté
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)
        
    def get_success_url(self):
        user = self.request.user
        if user.role == 'ETUDIANT': return '/dashboard/etudiant/'
        elif user.role == 'ENSEIGNANT': return '/dashboard/enseignant/'
        elif user.role == 'COORDINATEUR': return '/dashboard/coordinateur/'
        elif user.role == 'ADMINISTRATEUR': return '/dashboard/administrateur/'
        elif user.role == 'VICE_DOYEN': return '/dashboard/vice-doyen/'
        return '/admin/'

def is_etudiant(user): return user.is_authenticated and user.role == 'ETUDIANT'
def is_enseignant(user): return user.is_authenticated and user.role == 'ENSEIGNANT'
def is_coordinateur(user): return user.is_authenticated and user.role == 'COORDINATEUR'
def is_administrateur(user): return user.is_authenticated and user.role == 'ADMINISTRATEUR'
def is_vice_doyen(user): return user.is_authenticated and user.role == 'VICE_DOYEN'


# ==========================================
# GESTION DU PROFIL
# ==========================================
@login_required
def profil_utilisateur(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour avec succès.")
            return redirect('profil')
    else:
        form = UserProfileForm(instance=request.user, user=request.user)
        
    return render(request, '', {'form': form})


# ==========================================
# ESPACE ÉTUDIANT (STATUT 0)
# ==========================================
@user_passes_test(is_etudiant, login_url='/login/')
def dashboard_etudiant(request):
    conventions = Convention.objects.filter(etudiant=request.user).order_by('-date_creation')
    return render(request, 'conventions/dashboard_etudiant.html', {'conventions': conventions})

@user_passes_test(is_etudiant, login_url='/login/')
def creer_convention(request):
    if request.method == 'POST':
        form_entreprise = EntrepriseForm(request.POST)
        form_convention = ConventionForm(request.POST, request.FILES)
        if form_entreprise.is_valid() and form_convention.is_valid():
            entreprise = form_entreprise.save()
            convention = form_convention.save(commit=False)
            convention.entreprise = entreprise
            convention.etudiant = request.user
            
            # --- LE NOUVEAU CERVEAU DE ROUTAGE ---
            if convention.enseignant:
                convention.statut = 0 # Va chez l'encadrant choisi
                Notification.objects.create(utilisateur=convention.enseignant, message=f"Nouvelle convention à valider : {convention.etudiant.last_name}", lien="/dashboard/enseignant/")
            else:
                convention.statut = 1 # Va DIRECTEMENT chez le coordinateur de cette filière !
                if convention.filiere and convention.filiere.coordinateur:
                    Notification.objects.create(utilisateur=convention.filiere.coordinateur, message=f"Dossier sans encadrant à traiter : {convention.etudiant.last_name}", lien="/dashboard/coordinateur/")
            
            convention.save()
            return redirect('dashboard_etudiant')
    else:
        form_entreprise = EntrepriseForm()
        form_convention = ConventionForm()
    return render(request, 'conventions/creer_convention.html', {'form_entreprise': form_entreprise, 'form_convention': form_convention})
@login_required
def telecharger_convention(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id)
    
    # Sécurité : Un étudiant ne voit que SA convention FINALISÉE
    if request.user.role == 'ETUDIANT':
        if convention.etudiant != request.user:
            return HttpResponseForbidden("Accès non autorisé.")
        if convention.statut != 4:
            return HttpResponseForbidden("Ce document n'a pas encore été validé par le Vice-Doyen.")
    
    filepath = convention.document_pdf.path
    if os.path.exists(filepath):
        return FileResponse(open(filepath, 'rb'), content_type='application/pdf')
    return HttpResponseForbidden("Fichier introuvable sur le serveur.")


# ==========================================
# 1. ESPACE ENSEIGNANT (STATUT 0 -> 1)
# ==========================================
@user_passes_test(is_enseignant, login_url='/login/')
def dashboard_enseignant(request):
    attente = Convention.objects.filter(enseignant=request.user, statut=0).order_by('date_creation')
    validees = Convention.objects.filter(enseignant=request.user, statut__gte=1).order_by('-date_mise_a_jour')
    return render(request, 'conventions/dashboard_enseignant.html', {'attente': attente, 'validees': validees})

@user_passes_test(is_enseignant, login_url='/login/')
def valider_convention_enseignant(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id, enseignant=request.user, statut=0)
    if request.method == 'POST':
        if 'refuser' in request.POST:
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Aucun motif précisé.')
            convention.save()
            Notification.objects.create(utilisateur=convention.etudiant, message=f"❌ Convention refusée par l'encadrant. Motif: {convention.motif_rejet}", lien="/dashboard/etudiant/")
        else:
            convention.statut = 1
            convention.motif_rejet = None
            convention.save()
            coordinateurs = CustomUser.objects.filter(role='COORDINATEUR')
            for coord in coordinateurs:
                Notification.objects.create(utilisateur=coord, message=f"L'encadrant a validé la convention de {convention.etudiant.last_name}", lien="/dashboard/coordinateur/")
    return redirect('dashboard_enseignant')


# ==========================================
# 2. ESPACE COORDINATEUR (STATUT 1 -> 2)
# ==========================================
@user_passes_test(is_coordinateur, login_url='/login/')
def dashboard_coordinateur(request):
    # On récupère toutes les filières gérées par CE coordinateur
    mes_filieres = Filiere.objects.filter(coordinateur=request.user)
    
    # On filtre les conventions pour ne voir que celles de ses filières
    attente = Convention.objects.filter(statut=1, filiere__in=mes_filieres).order_by('date_creation')
    validees = Convention.objects.filter(statut__gte=2, filiere__in=mes_filieres).order_by('-date_mise_a_jour')
    
    # On récupère la liste de tous les enseignants pour le menu déroulant
    enseignants = CustomUser.objects.filter(role='ENSEIGNANT')
    
    return render(request, 'conventions/dashboard_coordinateur.html', {'attente': attente, 'validees': validees, 'enseignants': enseignants})


@user_passes_test(is_coordinateur, login_url='/login/')
def valider_convention_coordinateur(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id, statut=1)
    
    if request.method == 'POST':
        if 'refuser' in request.POST:
            # (Garde ton code de refus actuel ici)
            pass
            
        elif 'assigner_encadrant' in request.POST:
            # Le coordinateur a choisi un prof dans la liste
            prof_id = request.POST.get('nouvel_encadrant')
            if prof_id:
                prof = CustomUser.objects.get(id=prof_id)
                convention.enseignant = prof
                convention.statut = 0 # Le dossier redescend chez le prof !
                convention.save()
                Notification.objects.create(utilisateur=prof, message=f"Vous avez été assigné comme encadrant pour {convention.etudiant.last_name}", lien="/dashboard/enseignant/")
                messages.success(request, f"Dossier transféré au Pr. {prof.last_name}.")
                
        else: # Clic sur "Valider pour l'Administration" (avec ou sans encadrant)
            convention.statut = 2
            convention.save()
            admins = CustomUser.objects.filter(role='ADMINISTRATEUR')
            for admin in admins:
                Notification.objects.create(utilisateur=admin, message=f"Filière validée pour {convention.etudiant.last_name}", lien="/dashboard/administrateur/")
            messages.success(request, "Dossier validé et transmis à l'administration.")
            
    return redirect('dashboard_coordinateur')

# ==========================================
# 3. ESPACE ADMINISTRATEUR (STATUT 2 -> 3)
# ==========================================
@user_passes_test(is_administrateur, login_url='/login/')
def dashboard_administrateur(request):
    attente = Convention.objects.filter(statut=2).order_by('date_creation')
    validees = Convention.objects.filter(statut__gte=3).order_by('-date_mise_a_jour')
    return render(request, 'conventions/dashboard_administrateur.html', {'attente': attente, 'validees': validees})

@user_passes_test(is_administrateur, login_url='/login/')
def valider_convention_administrateur(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id, statut=2)
    
    if request.method == 'POST':
        coords = {
            'encadrant': (float(request.POST.get('x_enc', 0)), float(request.POST.get('y_enc', 0)), int(request.POST.get('page_enc', 1))),
            'coordinateur': (float(request.POST.get('x_coo', 0)), float(request.POST.get('y_coo', 0)), int(request.POST.get('page_coo', 1))),
            'doyen': (float(request.POST.get('x_doy', 0)), float(request.POST.get('y_doy', 0)), int(request.POST.get('page_doy', 1))),
        }
        if request.POST.get('action') == 'refuser':
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Aucun motif précisé.')
            convention.save()
            Notification.objects.create(utilisateur=convention.etudiant, message=f"❌ Convention rejetée par l'administration. Motif: {convention.motif_rejet}", lien="/dashboard/etudiant/")
            return redirect('dashboard_administrateur')
        # NOUVEAU : On sauvegarde les coordonnées du QR Code dans la base de données !
        convention.qr_x = float(request.POST.get('x_qr', 40))
        convention.qr_y = float(request.POST.get('y_qr', 40))
        convention.qr_page = int(request.POST.get('page_qr', 1))
        
        input_pdf = convention.document_pdf.path
        output_pdf = input_pdf.replace('.pdf', '_prepare.pdf')
        vice_doyen = CustomUser.objects.filter(role='VICE_DOYEN').first()
        
        success = apposer_3_tampons_libres(
            input_pdf_path=input_pdf, output_pdf_path=output_pdf,
            convention=convention, vice_doyen_user=vice_doyen, coords=coords
        )
        
        if success:
            convention.document_pdf.name = output_pdf.split('media/')[-1]
            convention.statut = 3 
            convention.save() # Sauvegarde le statut ET les coordonnées QR
            return redirect('dashboard_administrateur')

    return render(request, 'conventions/placer_3_signatures.html', {'convention': convention})
# ==========================================
# 4. ESPACE VICE-DOYEN (STATUT 3 -> 4)
# ==========================================
@user_passes_test(is_vice_doyen, login_url='/login/')
def dashboard_vice_doyen(request):
    attente = Convention.objects.filter(statut=3).order_by('date_creation')
    validees = Convention.objects.filter(statut=4).order_by('-date_mise_a_jour')
    
    # Statistiques KPI pour le doyen
    total_conventions = Convention.objects.count()
    conventions_en_cours = Convention.objects.filter(statut__lt=4).count()
    conventions_terminees = Convention.objects.filter(statut=4).count()
    total_entreprises = Entreprise.objects.count()
    
    stats_filieres = Convention.objects.values('etudiant__filiere').annotate(total=Count('id'))
    noms_filieres = [stat['etudiant__filiere'] or 'Non défini' for stat in stats_filieres]
    comptes_filieres = [stat['total'] for stat in stats_filieres]

    context = {
        'attente': attente,
        'validees': validees,
        'total_conventions': total_conventions,
        'conventions_en_cours': conventions_en_cours,
        'conventions_terminees': conventions_terminees,
        'total_entreprises': total_entreprises,
        'noms_filieres': noms_filieres,
        'comptes_filieres': comptes_filieres,
    }
    return render(request, 'conventions/dashboard_vice_doyen.html', context)

# ==========================================
# 4. ESPACE VICE-DOYEN (STATUT 3 -> 4)
# ==========================================
@user_passes_test(is_vice_doyen, login_url='/login/')
def valider_convention_vice_doyen(request, convention_id):
    convention = get_object_or_404(Convention, id=convention_id, statut=3)
    
    if request.method == 'POST':
        # 1. CAS DU REFUS
        if 'refuser' in request.POST:
            convention.statut = -1
            convention.motif_rejet = request.POST.get('motif_rejet', 'Aucun motif précisé.')
            convention.save()
            
            Notification.objects.create(
                utilisateur=convention.etudiant, 
                message=f"❌ Convention refusée par le Vice-Doyen. Motif: {convention.motif_rejet}", 
                lien="/dashboard/etudiant/"
            )
            messages.error(request, "Le dossier a été rejeté et renvoyé à l'étudiant.")
            return redirect('dashboard_vice_doyen')
            
        # 2. CAS DE L'APPROBATION (SCELLÉ FINAL)
        # On récupère l'emplacement exact choisi par l'Admin
        x_auto = convention.qr_x if convention.qr_x else 40
        y_auto = convention.qr_y if convention.qr_y else 40
        page_auto = convention.qr_page if convention.qr_page else 1
        
        input_pdf = convention.document_pdf.path
        output_pdf = input_pdf.replace('.pdf', '_VALIDE_FINAL.pdf')
        p12_path = os.path.join(settings.BASE_DIR, 'keystore', 'test_signer.p12')
        url_verification = request.build_absolute_uri(f'/convention/{convention.id}/telecharger/')
        
        # Le Vice-Doyen scelle le document cryptographiquement
        success = signer_document_pdf(
            input_pdf_path=input_pdf,
            output_pdf_path=output_pdf,
            p12_path=p12_path,
            p12_password='secret123',
            reason="Validation finale et scellé du décanat",
            location="Vice-Décanat",
            signer_name=f"Vice-Doyen {request.user.last_name}",
            x_coord=x_auto,
            y_coord=y_auto,
            qr_data=url_verification,
            page_number=page_auto,
            image_signature_path=None # L'image a déjà été placée par l'Admin à l'étape 3 !
        )
        
        if success:
            convention.document_pdf.name = output_pdf.split('media/')[-1]
            convention.statut = 4
            convention.save()
            
            # Notification de succès à l'étudiant
            Notification.objects.create(
                utilisateur=convention.etudiant,
                message="🎉 Félicitations ! Votre convention a été validée et scellée par le décanat.",
                lien="/dashboard/etudiant/"
            )
            messages.success(request, "Le document a été scellé cryptographiquement avec succès.")
            
    return redirect('dashboard_vice_doyen')


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q

@login_required
@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR')
def dashboard_mobilite(request):
    query = request.GET.get('search', '')
    # On ajoute un filtre pour voir les archives ou non (par défaut non)
    voir_archives = request.GET.get('archives', '0') == '1'

    mobilites = ConventionMobilite.objects.all().select_related('doctorant', 'type_convention')

    if voir_archives:
        mobilites = mobilites.filter(est_archive=True)
    else:
        mobilites = mobilites.filter(est_archive=False)

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

@login_required
@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR')
def archiver_mobilite(request, pk):
    mobilite = get_object_or_404(ConventionMobilite, pk=pk)
    # On bascule l'état (si archivé -> désarchive, si actif -> archive)
    mobilite.est_archive = not mobilite.est_archive
    mobilite.save()
    
    status = "archivée" if mobilite.est_archive else "restaurée"
    messages.success(request, f"La mobilité de {mobilite.doctorant.last_name} a été {status}.")
    
    return redirect('dashboard_mobilite')

@login_required
@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR')
def supprimer_mobilite(request, pk):
    mobilite = get_object_or_404(ConventionMobilite, pk=pk)
    if request.method == 'POST':
        nom = mobilite.doctorant.last_name
        mobilite.delete()
        messages.success(request, f"La mobilité de {nom} a été supprimée définitivement.")
    return redirect('dashboard_mobilite')

def notifications_globales(request):
    """Injecte les notifications non lues dans toutes les pages du site."""
    if request.user.is_authenticated:
        # On récupère les notifications non lues pour l'utilisateur connecté
        notifs = Notification.objects.filter(utilisateur=request.user, lu=False).order_by('-date_creation')
        return {
            'nb_notifs': notifs.count(),
            'notifs_non_lues': notifs[:5]  # On limite aux 5 plus récentes pour le menu déroulant
        }
    
    # Si l'utilisateur n'est pas connecté, on renvoie des valeurs vides
    return {
        'nb_notifs': 0,
        'notifs_non_lues': []
    }
# conventions/views.py
from django.db.models import Q

@user_passes_test(is_administrateur)
def dashboard_admin_alertes(request):
    # On cherche les mobilités où l'attestation est vide OU nulle
    # On utilise select_related('doctorant') pour charger les noms des étudiants d'un coup
    alertes_mobilite = ConventionMobilite.objects.filter(
        Q(contrat_signe__isnull=True) | Q(contrat_signe="")
    ).select_related('doctorant', 'type_convention')
    
    return render(request, 'conventions/admin_alertes.html', {
        'alertes_mobilite': alertes_mobilite,
        'total_alertes': alertes_mobilite.count()
    })

@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR', login_url='/login/')
def admin_ajouter_mobilite(request):
    if request.method == 'POST':
        form = ConventionMobiliteForm(request.POST, request.FILES)
        if form.is_valid():
            form.save() # Ici, le champ doctorant est dans le formulaire
            messages.success(request, "La mobilité a été enregistrée avec succès dans le système.")
            return redirect('dashboard_mobilite')
    else:
        form = ConventionMobiliteForm()
    
    return render(request, 'conventions/admin_ajouter_mobilite.html', {'form': form})


@login_required
@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR')
def liste_mobilites(request):
    # Récupérer l'année depuis l'URL (ex: ?annee=2024)
    annee_filtre = request.GET.get('annee')
    
    # Base de la requête
    mobilites = ConventionMobilite.objects.all().select_related('doctorant', 'type_convention')

    # Appliquer le filtre si une année est sélectionnée
    if annee_filtre:
        mobilites = mobilites.filter(annee_premiere_inscription=annee_filtre)

    # Récupérer la liste des années uniques pour le menu déroulant du filtre
    annees_disponibles = ConventionMobilite.objects.values_list('annee_premiere_inscription', flat=True).distinct().order_by('-annee_premiere_inscription')

    return render(request, 'conventions/liste_mobilites.html', {
        'mobilites': mobilites,
        'annees_disponibles': annees_disponibles,
        'annee_selectionnee': annee_filtre
    })

@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR')
def dashboard_alertes_mobilite(request):
    from django.utils import timezone
    aujourdhui = timezone.now().date()
    
    # On récupère les mobilités terminées mais sans attestation de retour
    alertes = ConventionMobilite.objects.filter(
        date_fin__lt=aujourdhui,
        attestation_retour=''
    ).select_related('doctorant')
    
    return render(request, 'conventions/admin_alertes_mobilite.html', {'alertes': alertes})


@user_passes_test(lambda u: u.role == 'ADMINISTRATEUR', login_url='/login/')
def modifier_mobilite(request, pk):
    # On récupère l'instance existante
    mobilite = get_object_or_404(ConventionMobilite, pk=pk)
    
    if request.method == 'POST':
        # 'instance=mobilite' permet de METTRE À JOUR et non de créer un doublon
        form = ConventionMobiliteForm(request.POST, request.FILES, instance=mobilite)
        if form.is_valid():
            form.save()
            messages.success(request, f"La mobilité de {mobilite.doctorant.last_name} a été mise à jour.")
            return redirect('dashboard_mobilite')
    else:
        form = ConventionMobiliteForm(instance=mobilite)
    
    return render(request, 'conventions/modifier_mobilite.html', {
        'form': form,
        'mobilite': mobilite
    })

