@echo off
chcp 65001 >nul
echo === Installation de ChatLocal ===
python --version >nul 2>&1 || (echo Python est introuvable. Installe-le depuis https://www.python.org puis relance ce fichier. & pause & exit /b 1)
python -m pip install -r requirements.txt
python scripts\create_shortcut.py
echo.
echo Termine ! Utilise le raccourci "Lancer ChatLocal" sur le Bureau.
pause
