from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from .views import *
urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'),
    path('nouvelle-convention/', creer_convention, name='creer_convention'),
    path('dashboard/etudiant/', dashboard_etudiant, name='dashboard_etudiant'),
    path('dashboard/enseignant/', dashboard_enseignant, name='dashboard_enseignant'),
    path('convention/<int:convention_id>/telecharger/', telecharger_convention, name='telecharger_convention'),
    path('dashboard/enseignant/', dashboard_enseignant, name='dashboard_enseignant'),
    path('convention/<int:convention_id>/valider-enseignant/', valider_convention_enseignant, name='valider_enseignant'),
    path('dashboard/coordinateur/', dashboard_coordinateur, name='dashboard_coordinateur'),
    path('convention/<int:convention_id>/valider-coordinateur/', valider_convention_coordinateur, name='valider_coordinateur'),
    path('dashboard/vice-doyen/', dashboard_vice_doyen, name='dashboard_vice_doyen'),
    path('convention/<int:convention_id>/valider-vice-doyen/', valider_convention_vice_doyen, name='valider_vice_doyen'),
    path('dashboard/administrateur/', dashboard_administrateur, name='dashboard_administrateur'),
    path('convention/<int:convention_id>/valider-administrateur/', valider_convention_administrateur, 	name='valider_administrateur'),
    # Espaces Administrateur
    path('dashboard/administrateur/', dashboard_administrateur, name='dashboard_administrateur'),
    path('convention/<int:convention_id>/valider-administrateur/', valider_convention_administrateur, name='valider_administrateur'),
    path('profil/', profil_utilisateur, name='profil'),
    path('', redirection_racine, name='home'),
  

    # ==========================================
    # URLs - MOBILITÉ DOCTORALE
    # ==========================================
    # Pour le doctorant

    path('administration/mobilite/nouvelle/', admin_ajouter_mobilite, name='ajouter_mobilite'),
    path('administration/mobilites/', dashboard_mobilite, name='dashboard_mobilite'),
    path('administration/mobilites/supprimer/<int:pk>/',supprimer_mobilite, name='supprimer_mobilite'),
    path('administration/mobilites/archiver/<int:pk>/', archiver_mobilite, name='archiver_mobilite'),
    path('administration/mobilites/modifier/<int:pk>/', modifier_mobilite, name='modifier_mobilite'),
]

