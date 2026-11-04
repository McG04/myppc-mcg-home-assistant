# myPPC (McG) 0.2.4 — integrare Home Assistant

Integrare nativă în `custom_components`, fără aplicație/add-on separat, fără
server, VNC, token API local sau port nou. Utilizatorul și parola sunt păstrate
în configurația locală Home Assistant și folosite la verificarea zilnică.

## Funcționare

Zilnic la **08:00, în fusul orar configurat în Home Assistant**, integrarea
pornește temporar un browser headless pentru
autentificarea normală în myPPC. Acesta lasă portalul să execute verificarea
reCAPTCHA invizibilă obișnuită; nu ocolește verificarea și nu rezolvă provocări.
După login, citește prin aceeași interfață web de date folosită de portal:

- Facturi: număr, dată, valoare curentă a facturii, rest individual de plată,
  scadență și stare achitat/neachitat.
- Plăți: numai dată, valoare, tip **OP** sau **APP**. Nu extrage seria sau
  numărul chitanței. O cheie locală internă previne duplicatele și păstrează
  numărul de plăți identice din aceeași zi.
- Sold net semnat din „Sold la zi”: −100 lei înseamnă avans disponibil 100 lei,
  de plată 0 lei. Soldul nu este reconstruit din istoricul incomplet.

Prima citire importă numai înregistrările oferite de paginile normale ale
portalului, fără căutări pentru date mai vechi sau paginare suplimentară.
Ulterior, păstrează istoricul local, adaugă noutățile și actualizează facturile
existente. Pentru plăți identice fără ID, păstrează multiplicitatea maximă
observată; nu poate distinge corecții ale unor tranzacții perfect identice.

Browserul este închis după login, iar sesiunea temporară este ștearsă după
copierea cookie-urilor numai în memoria procesului. Nu ține sesiunea activă
artificial și nu face trafic PPC între verificările programate. Coordinatorul
Home Assistant programează o citire pe zi. La repornire/reîncărcare se
restaurează istoricul salvat, fără o nouă autentificare. Dacă HA este oprit la
08:00, următoarea citire este în dimineața următoare. Numai prima instalare
fără istoric face o citire imediată. Erorile temporare nu declanșează
reautentificarea și nu provoacă încercări repetate în cursul zilei; următoarea
încercare este la 08:00. Datele vechi sunt păstrate, iar ultima citire reușită
rămâne vizibilă. O respingere explicită a parolei cere reautentificare.

Un timeout după trimiterea formularului nu înseamnă că sesiunea a expirat.
Versiunile anterioare clasificau și acest caz drept eroare de autentificare.
Reautentificarea verifică acum utilizatorul și parola printr-un login real în
portal înainte de salvare. Dacă parola este greșită, browserul lipsește sau
portalul nu confirmă conectarea, datele existente nu sunt modificate.
Reautentificarea păstrează codul de plată, istoricul și aceeași integrare;
nu citește facturile și plățile în timpul validării parolei.

## Instalare

### Prin HACS / Marketplace

1. Adaugă `https://github.com/McG04/myppc-mcg-home-assistant` ca
   repository personalizat de tip **Integration**.
2. Instalează **myPPC (McG)** și repornește Home Assistant.
3. Deschide **Setări → Dispozitive și servicii → Adaugă integrare**.

### Manual

1. Copiază folderul `custom_components/myppc_local` în
   `/config/custom_components/myppc_local` pe Home Assistant.
2. Repornește Home Assistant.
3. Setări → Dispozitive și servicii → Adaugă integrare → **myPPC (McG)**.
4. Introdu e-mailul/telefonul și parola myPPC. Codul de plată este opțional
   dacă în cont există un singur loc de consum; în celelalte cazuri specifică-l.
5. Asigură în prealabil browserul și driverul conform secțiunii următoare.
   După prima citire apar senzorii:
   Sold net, De plată, Avans disponibil, Ultima factură, Ultima plată,
   Istoric facturi, Istoric plăți și Ultima citire. Cei doi senzori de istoric
   expun în atribute toate datele importate din portal.

## Chromium și chromedriver furnizate de administrator

Integrarea necesită **Chromium și chromedriver deja instalate în același mediu
în care rulează procesul Home Assistant**. Caută `chromium` (sau
`chromium-browser`) și `chromedriver` în `PATH`. Versiunile browserului și ale
driverului trebuie să fie compatibile; folosește perechea oferită de aceeași
distribuție. Selenium rămâne o dependență Python declarată în manifest.

Integrarea nu descarcă și nu instalează pachete de sistem, nu copiază chei sau
repository-uri APK și nu creează ori execută scripturi wrapper pentru browser.
Dacă unul dintre executabile lipsește, citirea se oprește cu un mesaj explicit.
Nu se încearcă instalarea automată sau Selenium Manager pentru descărcarea driverului.

- **Home Assistant Core pe Linux:** administratorul instalează Chromium și
  chromedriver prin managerul distribuției înainte de configurarea integrării.
  Pe Debian, pachetele sunt `chromium` și `chromium-driver`. Executabilele
  trebuie să fie accesibile utilizatorului serviciului Home Assistant.
- **Home Assistant Container:** browserul și driverul trebuie incluse de
  administrator în imaginea containerului, la construirea imaginii, împreună
  cu bibliotecile necesare. Instalarea lor doar pe gazda Docker nu le face
  disponibile în container. Verifică din container, cu utilizatorul HA,
  comenzile `chromium --version` și `chromedriver --version`.
- **Home Assistant OS standard:** această versiune nu asigură automat browserul
  în containerul Core. Instalarea lui într-un terminal/add-on separat nu îl
  face accesibil integrării. O instalare HA OS fără executabilele necesare în
  Core nu este suportată de acest mod de autentificare; folosește un mediu
  Core/Container administrat în care poți furniza dependențele în prealabil.

Versiunile vechi puteau crea `.storage/myppc_local/runtime/alpine-browser`.
Noua versiune nu utilizează acel runtime și nu șterge automat fișierele lui.
Istoricul și configurarea existente sunt păstrate. Profilurile temporare ale
browserului sunt eliminate după fiecare login, inclusiv după reautentificare.
Chromium rulează headless, fără sandbox propriu, în mediul Home Assistant.

Datele de conectare și istoricul local intră în backup-urile HA care includ
configurația. Pachetul nu conține parole, cookie-uri sau date din contul tău.

## Stadiu și validare

Interfața reală a portalului a fost verificată prin browser. Metodele și câmpurile
de date sunt bazate pe codul public al frontend-ului PPC, nu pe endpoint-uri
ghicite. Autentificarea HTTP fără reCAPTCHA este refuzată de PPC; de aceea este
necesar browserul intern pentru login.

Au fost verificate local parsarea sumelor, soldul negativ, restul individual,
metodele OP/APP, duplicatele, persistența istoricului și reîncărcarea manuală.
Validările vechi ale runtime-ului instalat automat nu confirmă disponibilitatea
browserului în noua versiune: administratorul trebuie să furnizeze executabilele.
Testele de regresie acoperă lipsa browserului, validarea reautentificării,
păstrarea datelor și eliminarea profilului temporar. Aceste teste folosesc
dubluri de test pentru portal și nu confirmă un login live. Cazul PPC
`Rows: null` pentru lista fără facturi restante este tratat ca listă goală,
fără a înlocui soldul net cu zero. Dacă PPC cere o provocare suplimentară,
citirea se oprește și nu se afișează un sold fals.

## Versiunea 0.2.3

Corectează traducerea engleză de rezervă (`translations/en.json`). Traducerea română este păstrată.


## Versiunea 0.2.4

Elimină instalatorul de pachete de sistem. Folosește numai Chromium și
chromedriver furnizate în prealabil de administrator și validează parola
în portal înainte de salvarea datelor de reautentificare.
