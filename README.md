# myPPC (McG) 0.1.0 — integrare Home Assistant

Integrare nativă în `custom_components`, fără aplicație/add-on separat, fără
server, VNC, token API local sau port nou. Utilizatorul și parola sunt păstrate
în configurația locală Home Assistant și folosite la verificarea zilnică.

## Funcționare

O dată la 24 de ore, integrarea pornește temporar un browser headless pentru
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
Home Assistant programează o citire pe zi. Nu există o limită rigidă: o
reîncărcare manuală sau repornirea Home Assistant poate porni imediat o nouă
citire, inclusiv după o eroare.

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
5. Prima pregătire poate dura câteva minute. După prima citire apar senzorii:
   Sold net, De plată, Avans disponibil, Ultima factură, Ultima plată,
   Istoric facturi, Istoric plăți și Ultima citire. Cei doi senzori de istoric
   expun în atribute toate datele importate din portal.

## Browserul intern

Selenium este o dependență Python a integrării. Dacă Chromium și chromedriver
nu există deja, integrarea încearcă pregătirea unui runtime Alpine izolat în
`/config/.storage/myppc_local/runtime`, folosind `apk`, repository-urile și
cheile deja considerate de încredere în imaginea Core. Nu modifică pachetele
sistemului Core și nu cere mod privilegiat ori Protection mode dezactivat.

Runtime-ul poate ocupa câteva sute de MB, este păstrat între reporniri și este
folosit doar la verificarea zilnică. Sunt vizate HA OS/Core Alpine aarch64 și
amd64. Dacă `apk` sau cheile lipsesc, pregătirea se oprește cu eroare explicită.
Compatibilitatea exactă a browserului cu imaginea Core trebuie verificată pe Pi.
Chromium rulează fără sandbox propriu în containerul Core.

Datele de conectare și istoricul local intră în backup-urile HA care includ
configurația. Pachetul nu conține parole, cookie-uri sau date din contul tău.

## Stadiu și validare

Interfața reală a portalului a fost verificată prin browser. Metodele și câmpurile
de date sunt bazate pe codul public al frontend-ului PPC, nu pe endpoint-uri
ghicite. Autentificarea HTTP fără reCAPTCHA este refuzată de PPC; de aceea este
necesar browserul intern pentru login.

Au fost verificate local parsarea sumelor, soldul negativ, restul individual,
metodele OP/APP, duplicatele, persistența istoricului și reîncărcarea manuală.
Pe sistemul țintă au fost validate instalarea runtime-ului Alpine, loginul
headless, citirea portalului și cei opt senzori Home Assistant. Cazul PPC
`Rows: null` pentru lista fără facturi restante este tratat ca listă goală,
fără a înlocui soldul net cu zero. Dacă PPC cere o provocare suplimentară,
citirea se oprește și nu se afișează un sold fals.
