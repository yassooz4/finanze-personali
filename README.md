# Finanze personali · Google Sheets

App personale Python + Streamlit + Pandas. **Google Sheets è l'unico archivio online**: nessun database SQL, nessun salvataggio finanziario su disco Streamlit o GitHub. Il download Excel è solo una copia esportabile.

## Attivazione su Streamlit Cloud

1. Crea un foglio vuoto su https://sheets.new e chiamalo **Finanze**. L'app crea automaticamente le schede Movimenti, Arbitraggio, Categorie e Conti.
2. Su https://console.cloud.google.com crea o scegli un progetto. In **API e servizi > Libreria**, abilita **Google Sheets API**.
3. In **IAM e amministrazione > Account di servizio**, crea un account di servizio. Non serve assegnargli ruoli di amministrazione del progetto.
4. Apri l'account di servizio > **Chiavi > Aggiungi chiave > Crea nuova chiave > JSON**. Conserva il file privatamente.
5. Apri il foglio Google > **Condividi**. Aggiungi il `client_email` del JSON con ruolo **Editor**. Non rendere pubblico il foglio.
6. In Streamlit Cloud > app > **Settings > Secrets**, conserva `[accesso]` con la tua password e aggiungi `[sheets]` e `[gcp_service_account]` seguendo `secrets.example.toml`. Copia i valori del JSON nella sezione corrispondente. La `private_key` va su una stringa TOML con i caratteri `\n`, come nel modello. Non caricare il JSON o i Secrets su GitHub e non incollare le chiavi in chat.
7. In `[sheets]`, inserisci l'ID contenuto nel link: `https://docs.google.com/spreadsheets/d/QUESTO_E_L_ID/edit`. Salva i Secrets e riavvia l'app se necessario. Il ramo dell'app è **main**, file **app.py**. Puoi rimuovere la precedente sezione `[github]`: non viene più usata.
8. Registra una partita, apri il foglio per verificare la riga, riavvia l'app e verifica che la partita sia ancora presente.

Le vecchie partite non vengono importate automaticamente. Il precedente ramo `dati` resta intatto come archivio storico, ma l'app non lo usa più.

## Funzioni

### Budget e assistente gratuito

Apri **Assistente > Piano** e imposta periodo, limite totale delle uscite, conti da usare e riserva da conservare. Puoi conservare più periodi senza sovrapporli. Il limite comprende le uscite già registrate nel periodo. Le preferenze sono salvate insieme al piano e restano disponibili nelle nuove conversazioni.

In **Scadenze** aggiungi le spese ancora da pagare, comprese quelle scadute. Dopo aver registrato un pagamento nei Movimenti, collegalo all'impegno: l'accantonamento sparisce e conta l'importo effettivo del movimento. Ogni uscita può pagare un solo impegno. Prima di eliminare o spostare un movimento collegato, scollega l'impegno. Un impegno è una spesa singola; pagamenti parziali vanno suddivisi in più impegni.

Il margine è il minore fra limite residuo meno impegni e saldo dei conti meno impegni e riserva. I saldi includono i giroconti, che non consumano il budget. Le entrate da arbitraggio non incassate restano escluse. **Simula una spesa** e il riepilogo in Dashboard funzionano anche senza AI. Una simulazione considera una nuova spesa aggiuntiva, non il pagamento di un impegno già accantonato. I riferimenti giornalieri sono flessibili e arrotondati per difetto ai centesimi.

Per la chat:

1. Crea un account su https://console.groq.com e mantieni il piano **Free**, senza aggiungere fatturazione o passare a Developer.
2. Genera una chiave API e inseriscila soltanto in Streamlit Cloud > Settings > Secrets, nella sezione `[groq]` del modello `secrets.example.toml`. Dopo aver verificato il piano Free, imposta `free_plan_confirmed = true`. Non incollare chiavi in chat o su GitHub.
3. Apri la scheda Chat e abilita l'invio dei dati a Groq. Vengono inviati messaggi recenti, riepilogo del budget, categorie e preferenze, non credenziali o l'intero archivio. Il testo che scrivi viene trasmesso al servizio. Puoi cancellare la conversazione; il logout cancella anche lo stato della chat.

Puoi chiedere un riepilogo, simulare un acquisto, ottenere consigli sulle categorie del periodo e proporre un nuovo limite. Le modifiche al budget vengono validate e salvate solo dopo **Conferma nuovo budget**. Se dici quanto rimane da oggi, il piano esistente conserva lo storico e aggiunge le spese già registrate al nuovo limite totale. La chat non registra né elimina movimenti.

L'app non attiva abbonamenti, servizi alternativi o retry automatici. Su errore 429 si ferma e mostra che la quota è esaurita. Un limite aggiuntivo di 50 richieste al giorno per chiave e istanza e una pausa di 3 secondi riducono l'uso; questo contatore si azzera al riavvio e non sostituisce i limiti dell'account. **L'API non permette a questa app di verificare la fatturazione: la gratuità richiede che l'account resti Free.** Una chiave di un account Developer potrebbe generare addebiti anche con questa configurazione. Il modello è configurabile se Groq cambia disponibilità; non viene scelto automaticamente un altro modello.

I calcoli delle simulazioni vengono eseguiti dall'app in centesimi. I consigli testuali AI possono essere imprecisi: controlla sempre il riepilogo calcolato e mantieni aggiornati movimenti e scadenze. Non è stata effettuata una chiamata reale senza chiave. Condizioni e quote aggiornate: https://console.groq.com/docs/rate-limits e https://console.groq.com/docs/billing-faqs.

La migrazione aggiunge le schede **Budget** e **Impegni** a Google Sheets e all'export Excel, preservando le schede esistenti e le colonne personalizzate. Conserva una copia del foglio prima dell'aggiornamento; le vecchie versioni dell'app non gestiscono le nuove schede.

- Dashboard, movimenti con aggiunta/modifica/eliminazione, statistiche, conti e categorie personalizzabili.
- I moduli per creare e modificare movimenti, giroconti e partite si aprono su una schermata dedicata, con lo scorrimento normale della pagina anche da telefono. Torna indietro chiude il modulo senza salvare; dopo il salvataggio ritorni alla pagina di partenza.
- **Giroconto** in + Nuovo movimento: scegli conto di partenza, conto di arrivo e importo. Lo spostamento aggiorna entrambi i saldi e resta un unico record. In Movimenti, selezionando un conto compare come uscita dalla partenza o entrata nell'arrivo, con segno e riepiloghi coerenti. Nella vista Tutti e nelle statistiche generali non modifica guadagni o spese. Puoi modificarlo ed eliminarlo come gli altri movimenti.
- **Saldo attuale nei Movimenti**: mostra tutti i soldi del conto selezionato (o il totale di tutti i conti), incluso il saldo iniziale e i giroconti. Rimane indipendente dai filtri; entrate, uscite e differenza si riferiscono invece ai risultati filtrati.
- **Rinomina conti** in Gestione > Conti: seleziona il conto, scrivi il nuovo nome e premi Salva conto. La rinomina aggiorna movimenti, entrambi i conti dei giroconti e partite, mantenendo gli ID e i saldi.
- Arbitraggio: data (anche futura), numero pacco, squadre, compenso previsto, km, categoria della partita e note.
- Una partita nuova è **Da ricevere** e non aumenta il saldo. Se diventa **Ricevuto**, data incasso e conto sono richiesti e viene creata una sola entrata collegata. Le correzioni aggiornano la stessa entrata; il ritorno a Da ricevere la rimuove.
- Storico con stato, filtri, importi ricevuti e ancora da ricevere. Menu dei pagamenti nello storico.
- Login protetto dalla password nei Secrets e pulsante Esci.
- Gestione > Archivio: link al foglio e download di finanze.xlsx.

## Come vengono salvati i dati

Ogni lettura acquisisce i dati dal foglio e li elabora in Pandas. Viene memorizzata solo la connessione Google, mai una copia dei dati finanziari. I salvataggi aggiornano le schede interessate in un'unica richiesta Google atomica: partita e movimento vengono scritti insieme. Le cancellazioni rimuovono anche le righe residue; gli ID non cambiano nelle modifiche.

I giroconti sono righe di tipo `Giroconto` nella scheda `Movimenti`: `Conto` è la partenza e `Conto_destinazione` è l'arrivo. L'app aggiunge automaticamente questa colonna ai fogli esistenti, preservando le righe precedenti. Nella tabella dei conti, Accrediti e Addebiti includono gli spostamenti interni; le statistiche di guadagni e spese li escludono. Eliminare un conto richiede di riassegnare anche i giroconti; non è consentito unire i due conti di un giroconto senza prima modificarlo.

Le sessioni nella stessa istanza sono serializzate e prima del salvataggio viene verificato che il foglio non sia cambiato. Google Sheets non offre un blocco tra tutte le applicazioni: evita di modificare il foglio manualmente nello stesso istante di un salvataggio dall'app. Sono preservate schede aggiuntive e colonne personalizzate. Non rinominare le schede o le intestazioni dell'app e non cambiare gli ID; usa valori semplici nelle colonne finanziarie.

Se mancano credenziali o Google non risponde, l'app mostra un errore: non crea un archivio locale alternativo. Dopo un timeout verifica lo storico prima di reinserire una riga. Usa anche la cronologia versioni di Google Sheets per recuperare modifiche accidentali.

## Codice e test

`app.py`: login e navigazione; `sheets_storage.py`: Google Sheets; `service.py`: regole finanziarie e pagamenti; `analytics.py`: DataFrame e statistiche; `pages/`: interfaccia; `export.py`: copia Excel.

```bash
pip install -r requirements.txt
streamlit run app.py
```

In locale inserisci i Secrets in `.streamlit/secrets.toml` (ignorato da Git). Per i test isolati rimane l'adattatore Excel `storage.py`: è usato esclusivamente quando si imposta esplicitamente `FINANZE_FILE`, non come fallback online. Per eseguire i test: `pip install pytest`, poi `pytest -q`.
