# Aggiornamento: accesso con password

1. Streamlit → Manage app → Settings → Secrets: conserva [github] e aggiungi alla fine:

```toml
[accesso]
password = "LA_TUA_PASSWORD_PERSONALE"
```

Scegli una password lunga e unica. Non inserirla nei file del progetto o su GitHub.

2. Estrai il contenuto di questo ZIP direttamente nella cartella del progetto:
C:\Users\yassine.kouritta\Desktop\finanze
Accetta la sostituzione dei file. Lo ZIP non contiene finanze.xlsx e non modifica i dati.

3. Nel CMD esegui:

```bat
set "PATH=C:\Program Files\Git\cmd;%PATH%"
cd /d "C:\Users\yassine.kouritta\Desktop\finanze"
git switch main
git add app.py finanze_app/auth.py tests/test_auth.py tests/test_app.py tests/test_cloud_setup.py README.md secrets.example.toml ISTRUZIONI_LOGIN.md
git commit -m "Aggiunge accesso con password"
git push origin main
```

4. Streamlit aggiorna l’app automaticamente. Aprila in una finestra in incognito:
deve chiedere la password prima di mostrare dashboard, movimenti o saldi.
Prova una password errata, poi quella corretta. Esci riporta alla schermata di accesso.
Non creare pull request dal ramo dati.

Per cambiare la password modifica solo [accesso] nei Secrets. Le sessioni esistenti
richiederanno la nuova password al successivo aggiornamento. L’accesso dura per la
sessione del browser; un nuovo browser o una nuova sessione richiede la password.

Mantieni privato anche il repository GitHub: il file Excel resta consultabile da chi
ha accesso al repository, indipendentemente dalla password dell’app.

Test: python -m pytest tests -q
