from .models import Notification

def notifications_globales(request):
    """
    Ce processeur de contexte rend les notifications non lues 
    disponibles globalement dans tous les templates HTML.
    """
    # On vérifie d'abord si l'utilisateur est connecté pour éviter les erreurs
    if request.user.is_authenticated:
        # On récupère toutes les notifications de cet utilisateur qui n'ont pas encore été lues
        notifs_non_lues = Notification.objects.filter(
            utilisateur=request.user, 
            est_lue=False
        ).order_by('-date_creation')
        
        # On renvoie un dictionnaire qui sera accessible via les variables {{ notifs_non_lues }} et {{ nb_notifs }}
        return {
            'notifs_non_lues': notifs_non_lues,
            'nb_notifs': notifs_non_lues.count()
        }
        
    # Si l'utilisateur n'est pas connecté (ex: page de login), on renvoie un dictionnaire vide
    return {}
