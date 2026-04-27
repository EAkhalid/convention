from django import forms
from django.contrib.auth import get_user_model
from .models import (
    CustomUser, 
    Entreprise, 
    Convention, 
    ConventionMobilite, 
    Mobilite
)

User = get_user_model()

# --- Classes CSS Tailwind réutilisables ---
INPUT_CLASSES = 'w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
CHECKBOX_CLASSES = 'w-5 h-5 text-blue-600 rounded border-gray-300 focus:ring-blue-500 cursor-pointer'
FILE_CLASSES = 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer'

class UserProfileForm(forms.ModelForm):
    """Formulaire pour la mise à jour du profil (Nom, Email, Signature)"""
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'signature_image']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASSES}),
            'signature_image': forms.ClearableFileInput(attrs={'class': FILE_CLASSES}),
        }

class EntrepriseForm(forms.ModelForm):
    """Formulaire pour l'entreprise accueillant le stagiaire"""
    class Meta:
        model = Entreprise
        fields = ['nom', 'adresse', 'representant', 'ice']
        widgets = {
            'nom': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Nom de l\'entreprise'}),
            'adresse': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 3}),
            'representant': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Nom du signataire'}),
            'ice': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Ex: 0015... (Optionnel)'}),
        }

class ConventionForm(forms.ModelForm):
    """Formulaire pour la création de convention par l'étudiant"""
    class Meta:
        model = Convention
        fields = ['filiere', 'enseignant', 'sujet_stage', 'date_debut', 'date_fin', 'document_pdf']
        widgets = {
            'filiere': forms.Select(attrs={'class': INPUT_CLASSES}),
            'enseignant': forms.Select(attrs={'class': INPUT_CLASSES}),
            'sujet_stage': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Sujet du stage'}),
            'date_debut': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'date_fin': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'document_pdf': forms.ClearableFileInput(attrs={'class': FILE_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On limite le champ enseignant à ceux qui ont le rôle 'ENSEIGNANT'
        self.fields['enseignant'].queryset = CustomUser.objects.filter(role='ENSEIGNANT', is_active=True)
        self.fields['enseignant'].empty_label = "--- Aucun encadrant pour le moment ---"
        self.fields['document_pdf'].required = True




class MobiliteForm(forms.ModelForm):
    """Formulaire général pour les mobilités (lié directement à CustomUser)"""
    class Meta:
        model = Mobilite
        fields = [
            'etudiant', 
            'type_mobilite', 
            'destination', 
            'etablissement_accueil',
            'date_debut', 
            'date_fin', 
            'document_justificatif', 
            'etat'
        ]
        widgets = {
            'etudiant': forms.Select(attrs={'class': INPUT_CLASSES + ' select2'}),
            'type_mobilite': forms.Select(attrs={'class': INPUT_CLASSES}),
            'destination': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Ex: Paris, France'}),
            'etablissement_accueil': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Nom de l\'université ou du laboratoire'}),
            'date_debut': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'date_fin': forms.DateInput(attrs={'class': INPUT_CLASSES, 'type': 'date'}),
            'document_justificatif': forms.ClearableFileInput(attrs={'class': FILE_CLASSES}),
            'etat': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtre intelligent : on n'affiche que les utilisateurs actifs qui sont des étudiants
        self.fields['etudiant'].queryset = CustomUser.objects.filter(
            role__in=['DOCTORANT', 'MASTER', 'LICENCE'], 
            is_active=True
        ).order_by('last_name')
        
        # Rend le document facultatif dans le formulaire (sécurité supplémentaire)
        self.fields['document_justificatif'].required = False