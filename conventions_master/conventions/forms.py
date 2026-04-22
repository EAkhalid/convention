from django import forms
from .models import *



class ConventionForm(forms.ModelForm):
    class Meta:
        model = Convention
        # Ajoute bien 'filiere' et 'enseignant' à ta liste de champs
        fields = ['filiere', 'enseignant', 'document_pdf'] # (+ tes autres champs existants)
        
    def __init__(self, *args, **kwargs):
        super(ConventionForm, self).__init__(*args, **kwargs)
        # On indique visuellement à l'étudiant que l'encadrant n'est pas obligatoire
        if 'enseignant' in self.fields:
            self.fields['enseignant'].required = False
            self.fields['enseignant'].empty_label = "--- Aucun encadrant pour le moment ---"

class EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ['nom', 'adresse', 'representant', 'ice']


from django.contrib.auth import get_user_model
CustomUser = get_user_model()

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'signature_image']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'signature_image': 'Image de votre signature (Format PNG transparent recommandé)'
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600'}),
            'signature_image': forms.ClearableFileInput(attrs={'class': 'w-full px-4 py-2 border rounded-md text-gray-700 bg-gray-50'}),
        }

    # NOUVEAU : On modifie l'initialisation du formulaire
    def __init__(self, *args, **kwargs):
        # On extrait l'utilisateur passé en paramètre (s'il existe)
        self.user = kwargs.pop('user', None)
        super(UserProfileForm, self).__init__(*args, **kwargs)
        
        # Si l'utilisateur est un étudiant, on supprime carrément le champ signature
        if self.user and self.user.role == 'ETUDIANT':
            if 'signature_image' in self.fields:
                del self.fields['signature_image']





class ConventionMobiliteForm(forms.ModelForm):
    class Meta:
        model = ConventionMobilite  # <-- C'EST CETTE LIGNE QUI MANQUE
        fields = [
            'doctorant',
            'type_convention',
           
            'laboratoire_accueil', 
            'ville_pays', 
            'date_debut', 
            'date_fin', 
            'est_archive',
            'contrat_signe'
        ]
        widgets = {
            'doctorant': forms.Select(attrs={'class': 'select2-doctorant w-full w-full p-2 border border-gray-300 rounded select2'}),
            'type_convention': forms.Select(attrs={'class': 'w-full p-2 border rounded bg-white shadow-sm'}),
           
            'laboratoire_accueil': forms.TextInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded'}),
            'ville_pays': forms.TextInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded'}),
            'date_debut': forms.DateInput(attrs={'type': 'date', 'class': 'w-full p-2 border border-gray-300 rounded'}),
            'date_fin': forms.DateInput(attrs={'type': 'date', 'class': 'w-full p-2 border border-gray-300 rounded'}),
            'contrat_signe': forms.FileInput(attrs={'class': 'w-full p-2 border border-gray-300 rounded bg-gray-50'}),
            'est_archive': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On filtre pour n'afficher que les utilisateurs ayant le rôle ETUDIANT
        self.fields['doctorant'].queryset = CustomUser.objects.filter(role='DOCTORANT')
        self.fields['doctorant'].label_from_instance = lambda obj: f"{obj.last_name} {obj.first_name}"