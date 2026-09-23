# Guide de Déploiement en Ligne Gratuit (0€) — JARVIS / Ultron OS

Ce guide vous permet de mettre votre Jarvis en ligne gratuitement, sans carte bancaire obligatoire, avec une URL HTTPS sécurisée accessible depuis votre smartphone et votre PC.

---

## Option 1 : Render.com (100% Gratuit — Le plus simple, type Vercel)

### Étape 1 : Créer votre compte Render
1. Rendez-vous sur [render.com](https://render.com) et créez un compte gratuit (ou connectez-vous avec votre compte GitHub).

### Étape 2 : Connecter votre dépôt GitHub
1. Sur Render, cliquez sur le bouton bleu **New +** en haut à droite, puis sur **Blueprint** (ou **Web Service**).
2. Sélectionnez votre dépôt GitHub `Ultron-OS` (ou `jarvis-os`).
3. Render détecte automatiquement le fichier `render.yaml` préparé à la racine.

### Étape 3 : Renseigner votre clé Gemini
1. Dans les variables d'environnement demandées, entrez votre clé :
   - `GEMINI_API_KEY` : votre clé API Gemini (commençant par `AIza...` ou `AQ...`)
2. Cliquez sur **Apply** ou **Deploy**.
3. En ~2 minutes, Render vous donne votre URL publique sécurisée :  
   `https://ultron-os-jarvis.onrender.com`

> **Note sur le plan gratuit Render :** Si aucune interaction n'a lieu pendant 15 minutes, le serveur s'endort pour économiser les ressources et met ~30 secondes à se réveiller au premier clic. Pour le garder toujours éveillé, vous pouvez ajouter gratuitement l'URL `https://votre-jarvis.onrender.com/health` sur [cron-job.org](https://cron-job.org) ou [uptimerobot.com](https://uptimerobot.com) avec un ping toutes les 10 minutes.

---

## Option 2 : Hugging Face Spaces (100% Gratuit — Ne dort jamais)

Hugging Face Spaces propose un hébergement Docker gratuit avec 16 Go de RAM, processeur rapide, et sans mise en veille.

### Étape 1 : Créer un Space
1. Rendez-vous sur [huggingface.co](https://huggingface.co) et connectez-vous.
2. Cliquez sur votre profil > **New Space**.
3. Choisissez :
   - **Space name** : `jarvis-ultron-os`
   - **License** : MIT
   - **Space SDK** : **Docker** (Blank)
   - **Space Hardware** : CPU basic (Gratuit - 16 GB RAM)
   - **Visibility** : Private (ou Public si vous préférez)

### Étape 2 : Envoyer les fichiers
- Soit en connectant votre GitHub au Space.
- Soit en clonant le dépôt du Space et en y poussant les fichiers avec Git.

### Étape 3 : Configurer la variable secrète
1. Dans l'onglet **Settings** de votre Space > **Variables and secrets**.
2. Ajoutez un secret :
   - Name : `GEMINI_API_KEY`
   - Value : votre clé API Gemini
3. Votre Space compile automatiquement le `Dockerfile` et votre Jarvis est accessible immédiatement sur votre URL dédiée !

---

## Fonctionnalités disponibles en mode Cloud

| Fonctionnalité | En Cloud (Render / Hugging Face) | En Local (PC allumé) |
| :--- | :---: | :---: |
| **Dialogue vocal temps réel Gemini Live** | ✅ Oui (depuis PC ou smartphone) | ✅ Oui |
| **Interface HUD 3D, Orbe et Cartes Drag & Drop** | ✅ Oui | ✅ Oui |
| **Emails Hostinger Mail (lecture / envoi)** | ✅ Oui (24/7 même PC éteint) | ✅ Oui |
| **Prospection GetLeads & ScrapeGraph** | ✅ Oui (24/7 même PC éteint) | ✅ Oui |
| **Mémoire et base de données SQLite** | ✅ Oui (persistant) | ✅ Oui |
| **Ouvrir un onglet Comet sur votre écran physique** | ⚠️ Nécessite PC allumé + agent local | ✅ Oui direct |
| **Raccourcis clavier (Ctrl+T, Alt+F4) de votre Windows** | ⚠️ Nécessite PC allumé + agent local | ✅ Oui direct |
