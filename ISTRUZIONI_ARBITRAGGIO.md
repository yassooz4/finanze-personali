# Aggiornamento arbitraggio: pagamenti da ricevere

Estrai tutti i file di questo ZIP nella cartella del progetto finanze, accettando
la sostituzione. Lo ZIP contiene solo codice e istruzioni, senza finanze.xlsx.
Login e Secrets restano gli stessi. L'app aggiunge le nuove colonne nell'Excel.
Le partite già registrate restano Ricevuto e i loro saldi rimangono invariati.

CMD sul computer dove hai già il progetto:

```bat
set "PATH=C:\Program Files\Git\cmd;%PATH%"
cd /d "C:\Users\yassine.kouritta\Desktop\finanze"
git switch main
git add finanze_app/storage.py finanze_app/service.py finanze_app/ui.py finanze_app/pages/referee.py tests README.md ISTRUZIONI_ARBITRAGGIO.md
git commit -m "Arbitraggio: accredito solo al pagamento ricevuto"
git push origin main
```

Streamlit aggiorna automaticamente l'app. Non unire il ramo dati in main.

Uso:
- Nuova partita: Da ricevere, senza entrate o effetti sul saldo.
- Storico: menu Stato, Data incasso, Conto. Poi Salva pagamenti.
- Ricevuto: serve una data da quella della partita a oggi e un conto esistente.
- Da ricevere: rimuove l'eventuale entrata e cancella data incasso e conto.
- Per correggere una partita usa Modifica partita, anche quando è già pagata.
- I compensi mensili seguono la data della partita. Dashboard e movimenti seguono
  la data di incasso. I riepiloghi arbitraggio seguono i filtri sulle partite.
- Nessun incasso duplicato se risalvi lo stesso pagamento.

Da casa:
Puoi usare direttamente l'app online, senza installare nulla o trasferire il progetto.
Per modificare il codice, dopo aver installato Git apri il CMD:

```bat
cd /d "%USERPROFILE%\Desktop"
git clone https://github.com/yassooz4/finanze-personali.git
cd finanze-personali
```

Il progetto è già su GitHub. La copia del database autorevole è finanze.xlsx
sul ramo dati; quella su main è solo il modello iniziale.
Quando torni su un computer con una copia già clonata, prima di modificare:

```bat
git switch main
git pull --ff-only origin main
```

Test: python -m pytest tests -q
