import csv
import time
import random
import urllib.parse
import os
import traceback
import pandas as pd
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

# ---------------------------------------------------------
# Fonction de similarité
# ---------------------------------------------------------
def is_similar(a, b, threshold=0.55):
    if not a or not b or str(a) == 'nan' or str(b) == 'nan':
        return False
    ratio = SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()
    return ratio >= threshold

# ---------------------------------------------------------
# Configuration du Navigateur Anti-Bot
# ---------------------------------------------------------
def setup_driver():
    options = uc.ChromeOptions()
    # ATTENTION : Ne jamais utiliser options.add_argument("--headless") avec UC.
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=fr-FR")
    
    # CORRECTION : Le mode headless s'active ici directement, avec la version forcée.
    driver = uc.Chrome(options=options, headless=False, version_main=145)
    driver.implicitly_wait(5)
    return driver

# ---------------------------------------------------------
# Logique d'extraction
# ---------------------------------------------------------
# ---------------------------------------------------------
# Logique d'extraction (Version Debug & Cookies)
# ---------------------------------------------------------
def scrape_google_data(driver, nom, ville):
    query = urllib.parse.quote(f"{nom} {ville} Maroc")
    url_search = f"https://www.google.com/search?q={query}&hl=fr"
    
    try:
        driver.get(url_search)
        time.sleep(random.uniform(2.0, 3.5))
        if "sorry/index" in driver.current_url or "recaptcha" in driver.page_source.lower():
            print("\n🚨 CAPTCHA DÉTECTÉ ! 🚨")
            print("Google a temporairement bloqué l'accès.")
            print("1. Va sur la fenêtre Chrome ouverte par le script.")
            print("2. Résous le Captcha manuellement.")
            print("3. Attends que les résultats de recherche s'affichent.")
            input("👉 4. UNE FOIS LES RÉSULTATS AFFICHÉS, APPUIE SUR [ENTRÉE] ICI POUR CONTINUER...")
            print("Reprise du scraping...")
            time.sleep(2)
        # NOUVEAU : Tenter de cliquer sur le bouton "Tout accepter" pour les cookies
        try:
            boutons = driver.find_elements(By.XPATH, "//button[.//div[contains(text(), 'Tout accepter') or contains(text(), 'Accept all')]]")
            if boutons:
                boutons[0].click()
                time.sleep(1.5) # Attendre que la vraie page de recherche charge
        except:
            pass # Pas de page de cookies, on continue
            
    except Exception as e:
        print(f"  -> Erreur de chargement de la page : {e}")
        return None

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    data = {
        "Nom de recherche": nom,
        "Ville": ville,
        "Nom trouvé": "",
        "Secteur d'activité": "",
        "Adresse": "",
        "Téléphone": "",
        "Site Web": "",
        "Source Site Web": "Aucun"
    }
    
    # 1. Recherche dans la fiche Google (Knowledge Panel)
    rhs_panel = soup.find(id="rhs")
    
    if rhs_panel:
        title_node = rhs_panel.find(attrs={"data-attrid": "title"})
        if title_node: data["Nom trouvé"] = title_node.text.strip()
        
        subtitle_node = rhs_panel.find(attrs={"data-attrid": "subtitle"})
        if subtitle_node: data["Secteur d'activité"] = subtitle_node.text.strip()
        
        addr_node = rhs_panel.find(attrs={"data-attrid": "kc:/location/location:address"})
        if addr_node:
            val = addr_node.find(class_="LrzXr")
            if val: data["Adresse"] = val.text.strip()
            
        phone_node = rhs_panel.find(attrs={"data-attrid": "kc:/local:alt phone"})
        if phone_node:
            val = phone_node.find("span", class_="LrzXr") or phone_node.find("span", attrs={"aria-label": True})
            if val: data["Téléphone"] = val.text.strip()
            
        for a_tag in rhs_panel.find_all('a', href=True):
            text_link = a_tag.get_text(strip=True).lower()
            if "site web" in text_link or "website" in text_link:
                data["Site Web"] = a_tag['href']
                data["Source Site Web"] = "Fiche Google"
                break

    # 2. Fallback : 1er lien organique
    if not data["Site Web"]:
        first_result = None
        g_divs = soup.find_all('div', class_='g')
        for div in g_divs:
            a_tag = div.find('a', href=True)
            if a_tag and str(a_tag['href']).startswith('http'):
                first_result = a_tag
                break

        if first_result:
            url = first_result.get('href', '')
            title_node = first_result.find('h3')
            title_text = title_node.text if title_node else ""
            
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            domain_name = domain.split('.')[0] 
            
            # NOUVEAU : Affichage de ce que le script voit réellement
            print(f"    [Debug] 1er lien trouvé : {domain_name} | Titre : {title_text}")
            
            # J'ai abaissé le seuil de similarité à 0.45 pour être plus permissif
            if is_similar(nom, title_text, 0.45) or is_similar(nom, domain_name, 0.45):
                exclude_list = ['linkedin', 'facebook', 'instagram', 'telecontact', 'kerix', 'pagesjaunes', 'marocannuaire', 'kompass']
                if not any(ex in domain.lower() for ex in exclude_list):
                    data["Site Web"] = url
                    data["Source Site Web"] = "1er lien similaire"
            else:
                print("    [Debug] Lien ignoré : Nom trop différent de la recherche.")
                    
    return data

# ---------------------------------------------------------
# Exécution Principale
# ---------------------------------------------------------
def main():
    print("Démarrage du navigateur anti-bot...")
    try:
        driver = setup_driver()
    except Exception as e:
        print(f"Erreur lors du lancement du navigateur : {e}")
        traceback.print_exc()
        return

    output_file = 'output_entreprises.csv'
    fieldnames = ["Nom de recherche", "Ville", "Nom trouvé", "Secteur d'activité", "Adresse", "Téléphone", "Site Web", "Source Site Web"]
    
    # NOUVEAU : Lecture des entreprises déjà traitées pour la reprise automatique
    lignes_deja_traitees = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    lignes_deja_traitees.add(row.get("Nom de recherche", "").strip())
            print(f"🔄 Reprise activée : {len(lignes_deja_traitees)} entreprises déjà sauvegardées ignorées.")
        except Exception:
            pass
    else:
        with open(output_file, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    # Lecture robuste du CSV avec Pandas
    try:
        df = pd.read_csv('charika_ville.csv', sep=None, engine='python', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
    except Exception as e:
        print(f"Erreur impossible de lire df_nom_ville.csv : {e}")
        driver.quit()
        return

    if 'nom' not in df.columns or 'ville' not in df.columns:
        print("❌ ERREUR : Colonnes 'nom' et 'ville' introuvables.")
        driver.quit()
        return

    try:
        for index, row in df.iterrows():
            nom = str(row.get('nom', '')).strip()
            ville = str(row.get('ville', '')).strip()
            
            # Sécurité : Si vide ou déjà traité, on saute
            if not nom or nom.lower() == 'nan' or nom in lignes_deja_traitees:
                continue
                
            print(f"Recherche ({index + 1}/{len(df)}) : {nom} à {ville}...")
            
            result = scrape_google_data(driver, nom, ville)
            
            # Sauvegarde en temps réel
            if result:
                with open(output_file, mode='a', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(result)
                    
    except KeyboardInterrupt:
        print("\n⏹ Scraping interrompu manuellement.")
    except Exception as e:
        print(f"\n❌ Une erreur inattendue est survenue : {e}")
        traceback.print_exc()  # Affiche l'erreur exacte dans la console
    finally:
        print(f"\nFermeture du navigateur...")
        try:
            driver.quit()
        except Exception:
            pass
        print(f"Scraping terminé. Résultats sauvegardés dans '{output_file}'.")

if __name__ == "__main__":
    main()