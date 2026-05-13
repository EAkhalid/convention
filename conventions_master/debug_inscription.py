from conventions.models import SessionFormation, ParticipationFormation, InscriptionDoctorat
from django.db.models import Q

# 1. Configuration initiale
session_id = 23
sess = SessionFormation.objects.get(id=session_id)
catalogue = sess.formation

print("\n" + "="*50)
print(f"🔍 DEBUG LOGIQUE - SESSION {sess.id} : {catalogue.titre}")
print(f"Cibles : 1A:{catalogue.cible_1ere_annee} | 2A:{catalogue.cible_2eme_annee} | 3A:{catalogue.cible_3eme_annee} | 4A+:{catalogue.cible_4eme_annee_plus}")
try:
    annee_lancement = int(catalogue.annee)
except:
    annee_lancement = 0
print(f"Année de lancement du module : {annee_lancement}")
print("="*50)

inscriptions = InscriptionDoctorat.objects.filter(
    Q(annee_universitaire__startswith="2025") | Q(annee_universitaire__startswith="25"),
    est_valide=True
)

stats = {
    "flux_normal": 0,
    "rattrapage": 0,
    "deja_valide": 0,
    "trop_ancien": 0,
    "hors_cible": 0
}

details_flux = {}
details_rattrapage = {}

min_cible = 1 if catalogue.cible_1ere_annee else (2 if catalogue.cible_2eme_annee else (3 if catalogue.cible_3eme_annee else 4))

for ins in inscriptions:
    student = ins.student
    if student.user.is_superuser or student.id == 1: continue
    
    try:
        pai = int(float(str(student.PAI).strip()))
    except:
        continue
        
    annee_etude = 2026 - pai
    if annee_etude < 1: continue

    # TEST 1 : A-t-il déjà validé ?
    deja_valide = ParticipationFormation.objects.filter(
        student=student, session__formation=catalogue
    ).exclude(session=sess).filter(Q(presence=True) | Q(note__gte=10.0)).exists()

    if deja_valide:
        stats["deja_valide"] += 1
        continue 

    # TEST 2 : Est-il dans le Flux Normal ?
    dans_cible = False
    if catalogue.cible_1ere_annee and annee_etude == 1: dans_cible = True
    elif catalogue.cible_2eme_annee and annee_etude == 2: dans_cible = True
    elif catalogue.cible_3eme_annee and annee_etude == 3: dans_cible = True
    elif catalogue.cible_4eme_annee_plus and annee_etude >= 4: dans_cible = True

    if dans_cible:
        stats["flux_normal"] += 1
        details_flux[pai] = details_flux.get(pai, 0) + 1
        continue
        
    # TEST 3 : Est-il en Rattrapage ?
    if annee_etude > min_cible:
        if pai >= annee_lancement:
            stats["rattrapage"] += 1
            details_rattrapage[pai] = details_rattrapage.get(pai, 0) + 1
        else:
            stats["trop_ancien"] += 1
    else:
        stats["hors_cible"] += 1

print("\n📊 === RÉSULTATS DU DIAGNOSTIC ===")
print(f"✅ Inscrits (Flux Normal) : {stats['flux_normal']} --> Détail par PAI : {details_flux}")
print(f"✅ Inscrits (Rattrapage)  : {stats['rattrapage']} --> Détail par PAI : {details_rattrapage}")
print(f"🔥 TOTAL INSCRITS PRÉVUS  : {stats['flux_normal'] + stats['rattrapage']}")
print("-" * 35)
print(f"❌ Rejetés (Déjà Validé)  : {stats['deja_valide']}")
print(f"❌ Rejetés (Trop Ancien)  : {stats['trop_ancien']}")
print(f"❌ Rejetés (Hors Cible)   : {stats['hors_cible']}")
print("==================================================\n")