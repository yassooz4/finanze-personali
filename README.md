# Finanze — Streamlit Cloud + GitHub

App personale per movimenti, conti, categorie e arbitraggio. **finanze.xlsx è l'unico database.**
L'app si usa online da un indirizzo `https://....streamlit.app`, anche dal telefono.
Non devi avviare localhost o tenere acceso il computer.

## 1. Carica il progetto su GitHub

Crea un repository **privato**, ad esempio `finanze-personali`.
Estrai lo ZIP e carica **il contenuto** della cartella `finanze` nella radice del repository, non lo ZIP.
`app.py`, `requirements.txt` e `finanze.xlsx` devono essere nella radice.
Carica anche `finanze_app`, `tests`, `.gitignore` e `.streamlit/config.toml`.
Il ramo del codice sarà normalmente **main**.

## 2. Crea il ramo dati

Nel repository, apri il selettore del ramo `main`, scrivi `dati` e crea questo nuovo ramo da `main`.
Controlla che nel ramo **dati** sia presente `finanze.xlsx`.

- **main:** codice eseguito da Streamlit.
- **dati:** Excel aggiornato automaticamente dall'app.

Questa separazione evita che ogni movimento faccia ripartire l'app.
Dopo il primo salvataggio, l'Excel autorevole è quello sul ramo **dati**.
L'Excel iniziale su main non viene aggiornato e non va usato per controllare i saldi successivi.

## 3. Crea il token GitHub

In GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

- Scegli il tuo account come proprietario delle risorse.
- In **Repository access**, seleziona solo `finanze-personali`.
- In **Repository permissions → Contents**, imposta **Read and write**.
- Genera il token e copialo. Scegli una scadenza e rinnova il token nei Secrets prima che scada.

Il token va solo nei Secrets di Streamlit: non pubblicarlo nel codice o in un file GitHub.
`secrets.example.toml` contiene esclusivamente segnaposto.

## 4. Pubblica su Streamlit

Apri https://share.streamlit.io e collega GitHub, autorizzando l'accesso al repository privato.
Seleziona **Create app** e indica:

| Campo | Valore |
| --- | --- |
| Repository | `TUO_USERNAME/finanze-personali` |
| Branch del codice | `main` |
| Main file path | `app.py` |
| Python, nelle impostazioni avanzate | `3.12` |

In **Advanced settings → Secrets**, incolla e completa:

```toml
[github]
repository = "TUO_USERNAME/finanze-personali"
branch = "dati"
path = "finanze.xlsx"
token = "IL_TUO_TOKEN_GITHUB"

[accesso]
password = "SCEGLI_UNA_PASSWORD_LUNGA"
```

Salva e avvia il deploy. Mantieni l'app **privata** nelle impostazioni di condivisione.
L’app richiede anche la password personale configurata in [accesso]. Prima dell’accesso non legge l’archivio e non mostra le pagine finanziarie. Il pulsante Esci chiude la sessione. Se la password manca, l’app rimane bloccata.
Al termine apri l'indirizzo `https://....streamlit.app` assegnato alla tua app.

## Primo utilizzo

1. In **Gestione → Conti**, imposta i saldi iniziali e personalizza i conti.
2. Il saldo iniziale è ciò che avevi **prima del primo movimento registrato**.
   Esempio: 500 € iniziali + 100 € di entrate − 20 € di uscite = 580 €.
   Non registrare una seconda entrata per il saldo iniziale.
3. Usa **+ Nuovo movimento** per entrate e uscite.
4. Per le partite usa **Arbitraggio → + Nuova partita**: puoi inserire **Km percorsi** e
   **Categoria della partita** (testo libero, distinta dalla categoria finanziaria).
   I due campi sono modificabili anche dopo il pagamento e visibili nello storico.
   Per le partite già registrate, Km parte da 0 e Categoria partita resta vuota.
   Le colonne vengono aggiunte automaticamente all’Excel.
   Per i pagamenti, lo stato iniziale è **Da ricevere**,
   quindi il compenso non aumenta il saldo. Nello storico modifica **Stato**, **Data incasso**
   e **Conto**, poi premi **Salva pagamenti**. Lo stato **Ricevuto** genera una sola entrata
   alla data dell’incasso. Modificare o eliminare una partita aggiorna l’eventuale entrata.
   Tornare a **Da ricevere** rimuove l’entrata collegata e ricalcola il saldo.
   Puoi salvare più pagamenti insieme: se un dato è errato, nessuna modifica viene applicata.
   Le partite delle versioni precedenti mantengono lo stato **Ricevuto** e la data della loro
   entrata esistente, così l’aggiornamento non altera i saldi o duplica gli incassi.
5. Puoi creare, rinominare o eliminare tutte le categorie in **Gestione → Categorie**.

Il file iniziale non contiene movimenti di esempio: solo due conti a saldo zero e categorie modificabili.
I movimenti manuali riguardano importi già ricevuti o pagati, con date fino a oggi. Le partite distinguono compensi previsti da incassi effettivi. Le partite possono avere compenso zero.

## Come rimangono salvati i dati

L'app legge `finanze.xlsx` dal ramo `dati` a ogni aggiornamento. Quando salvi, modifica i fogli necessari
ed effettua **un unico commit dell'Excel su GitHub**. Mostra la conferma dopo il salvataggio remoto.

La copia sul server Streamlit è solo una cache ricostruibile: se viene eliminata o l'app riparte,
il file viene recuperato da GitHub. Se GitHub non è raggiungibile, l'app mostra un errore e non salva
solo nella cache. Se il file manca su un ramo accessibile, lo crea; crea anche i fogli mancanti.
Un Excel danneggiato produce un errore e non viene azzerato.

Gli aggiornamenti controllano lo SHA del file: due sessioni non possono sovrascrivere silenziosamente
le modifiche dell'altra. Se la connessione cade durante un salvataggio, l'app verifica se il commit
è già riuscito e non ripete automaticamente il movimento senza verificarlo.

Scarica l'Excel aggiornato da **Gestione → Archivio Excel** e aprilo normalmente con Excel.
Le versioni precedenti rimangono nella cronologia GitHub del file sul ramo `dati`.
Per ripristinare una versione, conserva prima una copia dell'ultima e sostituisci il file
**sul ramo dati**, quindi premi **Aggiorna dati**.

Usa l'app per modificare partite, categorie e conti, così i collegamenti restano coerenti.
Non cambiare manualmente ID, intestazioni o il movimento collegato a una partita in Excel.

## Gestione dello storico

- Movimenti: filtri per data, tipo, conto e categoria, ricerca e area di modifica/eliminazione.
- Arbitraggio: mese, anno o periodo, totale guadagnato, media e storico delle partite.
- Statistiche: saldo nel tempo, confronto mensile e ripartizione per categoria/provenienza.
- Rinomine di conti e categorie: aggiornano anche lo storico.
- Eliminazione categoria: conserva i movimenti, riclassificandoli o lasciandoli senza categoria.
- Eliminazione conto con dati: richiede un altro conto a cui riassegnare movimenti e saldo iniziale.
  Il totale generale rimane invariato.

## Fogli Excel

| Foglio | Colonne |
| --- | --- |
| Movimenti | ID, Data, Tipo, Importo, Categoria, Descrizione, Fonte, Note, Data_creazione, Conto, Arbitraggio_ID |
| Arbitraggio | ID, Data partita, Numero pacco, Squadra casa, Squadra ospite, Compenso, Note, Conto, Movimento_ID, Categoria |
| Categorie | ID, Nome, Tipo |
| Conti | ID, Nome, Saldo_iniziale |

Date e importi sono valori Excel reali. Il numero pacco è testo e conserva gli zeri iniziali.
Saldi e totali si calcolano in centesimi. Arbitraggio include anche le colonne Stato e Data incasso, aggiunte automaticamente.
Il grafico del saldo include i movimenti precedenti al periodo scelto.

## File principali

- `app.py`: avvio su Streamlit Cloud e lettura dei Secrets.
- `finanze_app/github_storage.py`: Excel persistente, concorrenza e verifica salvataggi.
- `finanze_app/storage.py`: lettura/scrittura Excel con openpyxl.
- `finanze_app/service.py`: movimenti, partite, conti e categorie.
- `finanze_app/analytics.py`: saldi e statistiche.
- `finanze_app/ui.py`, `styles.css`, `pages/`: moduli, grafici e layout responsive.
- `secrets.example.toml`: modello da completare nei Secrets di Streamlit.

## Solo per lo sviluppo

I test usano file temporanei e un GitHub simulato, senza modificare repository reali:

```bash
python -m pip install -r requirements.txt pytest
python -m pytest tests -q
```

La variabile `FINANZE_FILE` permette un Excel locale per lo sviluppo offline.
Senza questa variabile, l'app richiede la configurazione GitHub e non ripiega sui soli file del server.

Documentazione ufficiale:

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- https://docs.streamlit.io/develop/concepts/connections/connecting-to-data
- https://docs.github.com/en/rest/repos/contents
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
