<div align="center">

<img src="assets/logo_512.png?v=1795435439" alt="Logo ChatLocal" width="120">

<h1>ChatLocal</h1>

<p><b>Ton assistant IA de bureau : rapide, élégant et privé.</b><br>

### 🏠 L'écran d'accueil

- **Barre du haut** : boutons précédent / suivant, affichage de l'historique, et les menus **Fichier**, **Modifier**, **Affichage** et **Aide**.
- **Barre d'icônes à gauche** : l'accueil, la **comparaison de deux modèles**, l'**historique** des discussions, la page **Toutes les discussions** (sélection et actions groupées) et le menu `⋯`.
- **Zone de saisie** : le `+` joint des fichiers, le nom du modèle (en bas à droite de la barre) permet d'en changer, la flèche envoie le message.
- **Raccourcis sous la barre** : des débuts de phrase prêts à l'emploi pour créer une image ou écrire un texte.
- **Icône en haut à droite** : démarre un **chat éphémère**, qui n'est jamais enregistré.
Discute avec tes modèles locaux <a href="https://ollama.com">Ollama</a> ou avec les modèles NVIDIA, dans une interface sombre soignée.</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/Ollama-100%25%20local-000000?style=for-the-badge" alt="Ollama">
  <img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows">
</p>

<p>
  <a href="https://raw.githubusercontent.com/alexmrgy/ChatLocal/main/download/ChatLocal.exe?v=1795435689">
    <img src="https://img.shields.io/badge/%E2%AC%87%EF%B8%8F%20T%C3%A9l%C3%A9charger-ChatLocal-4867be?style=for-the-badge&logo=windows&logoColor=white" alt="Télécharger ChatLocal">
  </a>
</p>

<p>
  <a href="#-aperçu">Aperçu</a> ·
  <a href="#-fonctionnalités">Fonctionnalités</a> ·
  <a href="#-installation">Installation</a> ·
  <a href="#️-raccourcis">Raccourcis</a> ·
  <a href="#️-structure">Structure</a>
</p>

<img src="docs/screenshot.png?v=1795435938" alt="Capture d'écran de ChatLocal" width="820">

</div>

<br>

## 🎯 Aperçu

ChatLocal est une application de bureau pour discuter avec une IA **sans passer par un site web**.
Tes conversations sont enregistrées sur ton PC, rangées dans des dossiers, et tu peux écrire, éditer et même
**exécuter le code** que l'IA te propose, sans quitter la fenêtre.

## ✨ Fonctionnalités

| | |
|---|---|
| 🤖 **100 % local** | Utilise tes modèles Ollama : rien ne quitte ton ordinateur. |
| ☁️ **Modèles NVIDIA** | Ajoute ta clé API pour utiliser les modèles hébergés. La clé est chiffrée sur disque (DPAPI Windows). |
| 🗂️ **Historique organisé** | Dossiers, épinglage, archivage, renommage, déplacement et recherche rapide. Sélection multiple (`Ctrl` + clic, `Maj` + clic) pour archiver ou supprimer plusieurs discussions d'un coup. Glisse-dépose une ou plusieurs discussions sur un dossier pour les ranger. |
| 📎 **Fichiers joints** | Bouton `+` ou glisser-déposer : fichiers texte et code (lus par le modèle) et images (modèles Ollama avec vision). |
| ⚖️ **Comparaison de modèles** | Suis une vraie conversation avec deux modèles à la fois : réponses côte à côte, chacun se souvient de ses propres réponses, avec temps de réponse et longueur (`Ctrl+Maj+M`). Les comparaisons sont enregistrées dans l'historique et se rouvrent comme une conversation. |
| 🇫🇷 **Réponses en français** | Tous les modèles répondent toujours en français, avec des emojis adaptés au sujet. |
| 🕐 **Heure du PC** | Tous les modèles connaissent la date et l'heure de ton ordinateur et peuvent te les donner si tu les demandes. |
| 🕶️ **Chat éphémère** | Une conversation qui n'est jamais enregistrée. |
| 🧑‍💻 **Panneau de code** | Les longs blocs de code s'ouvrent à droite, dans un éditeur avec numéros de ligne et coloration. |
| ▶️ **Terminal intégré** | Lance du code Python ou C directement depuis la réponse. |
| ✏️ **Édition et versions** | Modifie un message et retrouve les différentes versions d'une réponse. |
| 📝 **Markdown complet** | Titres, listes, tableaux, citation d'un passage, copie de la dernière réponse. |
| 🎨 **Thème sombre** | Interface épurée avec la police Nunito, fournie avec l'application. |

## 🖼️ Visite guidée

Chaque capture est suivie de l'explication de ses différentes parties.

### 💬 La discussion

<p align="center">
  <img src="docs/chat.png?v=1795435938" alt="Une discussion" width="860">
</p>

- **Titre en haut** : le nom de la discussion. Clique dessus pour la renommer, l'épingler, la verrouiller, l'archiver, la copier ou la partager. La petite icône à gauche démarre un **nouveau chat**, celle de droite ouvre un **chat éphémère** (jamais enregistré).
- **Bulle bleue** : ta question. Passe la souris dessus pour la **copier** ou la **modifier** : l'ancienne version reste consultable avec les flèches `‹ 1/2 ›`.
- **Réponse de l'IA** : affichée en Markdown (titres, listes, tableaux, gras…), avec un bouton pour **copier** toute la réponse.
- **Bloc de code** : coloration automatique, bouton **copier** et bouton **ouvrir à droite** (voir plus bas).
- **Barre du bas** : le `+` joint des fichiers, le nom du modèle permet d'en changer, la flèche envoie (ou arrête la réponse en cours).

### 🗂️ L'historique, les dossiers et les épinglés

<p align="center">
  <img src="docs/history.png?v=1795435938" alt="Historique des discussions" width="860">
</p>

- **Épinglés** : les discussions importantes restent en haut de la liste.
- **Dossiers** : crée-en avec le `+`, donne-leur une couleur (clic droit sur le dossier) et range-y tes discussions. Un dossier se replie ou se déplie d'un clic.
- **Récents** : toutes les autres discussions, de la plus récente à la plus ancienne. Au survol, une punaise et un menu `⋯` apparaissent sur chaque ligne.
- **Glisser-déposer** : prends une discussion avec la souris et lâche-la sur un dossier pour la ranger, ou sur le fond de la liste pour la sortir du dossier.
- **Loupe en haut** : ouvre la recherche rapide (`Ctrl+K`).

### ☑️ Sélectionner plusieurs discussions

<p align="center">
  <img src="docs/selection.png?v=1795435938" alt="Sélection multiple" width="860">
</p>

- **`Ctrl` + clic** ajoute ou retire une discussion de la sélection ; **`Maj` + clic** sélectionne toute une plage. Les lignes sélectionnées passent en bleu.
- **Barre du bas** : indique le nombre de discussions choisies et propose **Archiver** ou **Supprimer** pour toutes d'un coup (la suppression demande une confirmation).
- **Raccourcis** : `Suppr` supprime la sélection, `Échap` l'annule.
- Tu peux aussi **glisser toute la sélection** vers un dossier.

### 📁 Déplacer une discussion dans un dossier

<p align="center">
  <img src="docs/move_menu.png?v=1795435938" alt="Menu pour déplacer une discussion" width="860">
</p>

- Ouvre le menu `⋯` (ou clic droit) d'une discussion puis **Déplacer vers un dossier**.
- La liste montre tes dossiers avec leur couleur ; une **coche** indique le dossier actuel.
- **Retirer du dossier** ramène la discussion dans les Récents, et **Nouveau dossier…** crée un dossier et y range tout de suite la discussion.

### 🧑‍💻 Le panneau de code et le terminal

<p align="center">
  <img src="docs/code.png?v=1795435938" alt="Panneau de code" width="860">
</p>

- **Ouvrir à droite** : le bouton du bloc de code l'affiche dans un éditeur avec **numéros de ligne** et **coloration**. Les codes longs s'y ouvrent automatiquement.
- **Bouton ▶ vert** : lance le code (Python ou C) et affiche le résultat dans un **terminal intégré** (bouton à côté).
- **Modifiable** : tu corriges le code directement, il est enregistré automatiquement dans la discussion.
- **Barre d'outils** : copier le code, l'enregistrer dans un fichier, fermer le panneau.

### 📎 Joindre des fichiers

<p align="center">
  <img src="docs/files.png?v=1795435938" alt="Fichiers joints" width="860">
</p>

- Clique sur le `+` ou **glisse-dépose** des fichiers sur la barre de saisie.
- Chaque fichier devient une **pastille** (avec une croix pour le retirer avant l'envoi).
- Les fichiers **texte et code** sont lus et transmis au modèle ; les **images** sont envoyées aux modèles Ollama qui savent les voir.
- Si tu n'écris rien, la question « Analyse le fichier joint. » est ajoutée.

### 🤖 Choisir le modèle

<p align="center">
  <img src="docs/models.png?v=1795435938" alt="Choix du modèle" width="860">
</p>

- Clique sur le nom du modèle dans la barre de saisie : la liste montre tous tes modèles **Ollama** installés, avec une coche sur celui utilisé.
- **Ajouter une clé API NVIDIA** donne accès aux modèles NVIDIA hébergés, ajoutés à la même liste.
- Le choix est mémorisé **par discussion**. Un clic droit sur un modèle permet de lui donner un nom plus simple.

### ⚖️ Comparer deux modèles

<p align="center">
  <img src="docs/compare.png?v=1795435938" alt="Comparaison de deux modèles" width="860">
</p>

- **Deux listes en haut** : choisis le modèle A et le modèle B (`Ctrl+Maj+M` ouvre la page).
- **Une seule question** : les deux modèles répondent en même temps, côte à côte.
- **Sous chaque réponse** : le temps total, le délai avant le premier mot et le nombre de caractères, pour juger rapidité et longueur.
- **La conversation continue** : chaque modèle se souvient de ses propres réponses. **Nouvelle comparaison** repart de zéro, et chaque comparaison est enregistrée dans l'historique.

### 🔎 La recherche rapide

<p align="center">
  <img src="docs/search.png?v=1795435938" alt="Recherche rapide" width="860">
</p>

- `Ctrl+K` (ou la loupe) ouvre une fenêtre au centre : tape quelques lettres pour retrouver une discussion par son titre.
- **Actions rapides** : par exemple « Nouveau chat » avec son raccourci.
- **Onglets du bas** : *Tout*, *Actions* ou *Chats* pour filtrer les résultats.

## 🚀 Installation

### ⬇️ Le plus simple : télécharger l'application

1. **[Télécharge ChatLocal](https://raw.githubusercontent.com/alexmrgy/ChatLocal/main/download/ChatLocal.exe?v=1795435689)** (environ 40 Mo).
2. Double-clique dessus : rien à installer.
3. Installe [Ollama](https://ollama.com) si ce n'est pas déjà fait, puis `ollama pull gemma3` pour avoir un modèle.

> ⚠️ **Windows bloque le fichier ?** L'application n'est pas signée, donc Windows peut afficher
> « Une stratégie de contrôle d'application a bloqué ce fichier » ou « Windows a protégé votre ordinateur ».
> Deux solutions :
> - **Débloquer le fichier** : clic droit sur le fichier **ChatLocal** téléchargé → **Propriétés** → coche **Débloquer** en bas → **OK**
>   (ou **Informations complémentaires** → **Exécuter quand même** pour SmartScreen).
> - **Sans exécutable** : installe Python, puis lance `ChatLocal.pyw` (double-clic), voir la section ci-dessous.

### 🧑‍💻 Depuis le code source

**Prérequis :** Windows, Python 3.10+ et [Ollama](https://ollama.com) avec au moins un modèle installé.

```powershell
git clone https://github.com/alexmrgy/ChatLocal.git
cd ChatLocal
pip install -r requirements.txt
ollama pull gemma3
python main.py
```

Tu peux aussi double-cliquer sur `ChatLocal.pyw` : même application, sans fenêtre de console.

> 💡 `gemma3` n'est qu'un exemple : n'importe quel modèle Ollama fonctionne.

### 📦 Créer l'application Windows

Un seul fichier ChatLocal, sans console et avec son icône, à lancer par double-clic :

```powershell
pip install pyinstaller
python scripts/build_exe.py
```

Le résultat se trouve dans le dossier `dist/` (environ 40 Mo) et une copie dans `download/`, utilisée par le bouton de téléchargement. Ollama doit toujours être installé séparément,
et Python doit être installé si tu veux lancer du code Python depuis le terminal intégré.

## ⌨️ Raccourcis

<details open>
<summary><b>Voir tous les raccourcis</b></summary>

<br>

| Raccourci | Action |
|---|---|
| `Ctrl` + `N` | Nouvelle conversation |
| `Ctrl` + `Maj` + `N` | Chat éphémère |
| `Ctrl` + `K` / `Ctrl` + `F` | Rechercher |
| `Ctrl` + `B` | Afficher / masquer l'historique |
| `Ctrl` + `Maj` + `L` | Toutes les discussions |
| `Ctrl` + `Maj` + `M` | Comparer deux modèles |
| `F2` | Renommer la conversation |
| `Ctrl` + `Alt` + `P` | Épingler / désépingler |
| `Ctrl` + `Maj` + `A` | Archiver |
| `Ctrl` + `Maj` + `C` | Copier la dernière réponse |
| `F5` | Actualiser les modèles |
| `F11` | Plein écran |
| `Échap` | Arrêter la génération |

</details>

## 🗃️ Structure

```text
ChatLocal/
├── main.py            point d'entrée
├── ChatLocal.pyw      lanceur par double-clic (sans console, sans application à télécharger)
├── attachments.py     lecture et limites des fichiers joints
├── system_prompt.py   consignes envoyées aux modèles (français, emojis, heure du PC)
├── ui/                interface PySide6 (fenêtre, chat, sidebar, éditeur, terminal…)
├── ollama/            client HTTP Ollama et threads de génération
├── nvidia/            client de l'API NVIDIA
├── database/          base SQLite et chiffrement des clés
├── styles/            thème sombre (dark.qss)
├── assets/            polices et icônes SVG
├── scripts/           logo, application Windows, captures d'écran du README
├── download/          ChatLocal (application prête à l'emploi)
├── tests/             tests automatiques
└── docs/              captures d'écran du README
```

## ⚙️ Configuration

| Variable d'environnement | Rôle | Valeur par défaut |
|---|---|---|
| `OLLAMA_HOST` | Adresse du serveur Ollama | `http://localhost:11434` |
| `NVIDIA_BASE_URL` | Adresse de l'API NVIDIA | `https://integrate.api.nvidia.com/v1` |
| `CHATLOCAL_DATA_DIR` | Dossier des données | `%APPDATA%\ChatLocal` |

## 🧪 Tests

Chaque fichier de `tests/` est un script indépendant, à lancer depuis la racine du projet :

```powershell
python tests/db_test.py
python tests/render_test.py
```

Certains tests demandent qu'Ollama soit lancé avec un modèle installé.

## 🔒 Confidentialité

Les conversations sont stockées dans une base SQLite locale. Avec Ollama, **aucune donnée ne quitte ta machine**.
Seuls les modèles NVIDIA envoient tes messages à l'API NVIDIA.

## 🛠️ Technologies

[Python](https://www.python.org) · [PySide6 / Qt](https://doc.qt.io/qtforpython-6/) · [Ollama](https://ollama.com) · SQLite · [Pygments](https://pygments.org) · [Markdown](https://python-markdown.github.io)

## 📄 Licence

La police Nunito est sous licence OFL (voir `assets/fonts/OFL-Nunito.txt`).

<div align="center">
<br>
<sub>Fait avec ❤️ en Python</sub>
</div>
