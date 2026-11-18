# Prüfstand für deutsche Unternehmen

Prüfstand prüft Agenten vor dem Produktiveinsatz: nachvollziehbare Werkzeugaufrufe, reproduzierbare Fehler, kontrollierte Störungen und technische Nachweise für die gemeinsame Bewertung durch Engineering, Risikomanagement und Datenschutz.

## Deutsch-Testsuite

Acht synthetische Abläufe: Rückerstattung, Rechnungsbuchung, Schadensregulierung, Überweisung, Vertragskündigung, Bestellfreigabe, Konstruktionsfreigabe und Terminbestätigung. Die Regeln prüfen formelle Ansprache, deutsche Geldbeträge (`1.234,56 €`), explizite Datumsangaben, Fachbegriffe mit Umlauten und eine KI-Kennzeichnung. Das ist eine nachvollziehbare Regelprüfung, keine allgemeine Messung sprachlicher Qualität.

## DSGVO-bezogene Datenprüfung

Vor dem Speichern werden verschachtelte Eingaben, Ausgaben und Fehlermeldungen auf bekannte Muster geprüft. IBANs, E-Mail-Adressen, mögliche Steuer-IDs, deutsche Adressen, Gesundheitsbegriffe und Zugangsdaten werden standardmäßig maskiert. Findings enthalten Kategorien und Feldpfade, keine gefundenen Werte. Numerische oder unerwartet formatierte personenbezogene Daten können übersehen werden. Es gibt Fehlalarme und unerkannte Daten; rechtliche Anforderungen werden dadurch nicht automatisch erfüllt.

Rohdaten verlassen die Werkzeuge weiterhin unverändert. Optionaler Rohmitschnitt (`redact=False`) erfordert eine eigenverantwortlich festgelegte Daten- und Zugriffspolitik. Evidenzexporte werden erneut geprüft. Es werden weder automatische Löschfristen noch Zugriffskontrollen für gemeinsam genutzte Datenbanken behauptet.

## Technisches Evidenzpaket

`pruefstand evidence` erzeugt ein ZIP mit Trace-Export, Profilen, Beobachtungen zu Kennzeichnung und Aufsicht sowie SHA-256-Manifest. Das Paket unterstützt eine menschliche Governance-Prüfung. Es stellt keine Rechtsberatung, kein Audit-Testat und keine Bestätigung der Erfüllung des EU AI Acts dar. Aktuelle Pflichten und Anwendbarkeit müssen Fachleute anhand des konkreten Einsatzes bewerten; das Projekt übernimmt keine ungeprüften Fristen aus dem ursprünglichen Projektplan.

## Souveräne Modelle

OpenAI-kompatible Endpunkte können lokal oder auf einer ausdrücklich konfigurierten Infrastruktur betrieben werden. Die Hostliste dokumentiert nur eine Angabe des Betreibers. Sie prüft keine tatsächlichen Verarbeitungsorte, Unterauftragnehmer oder Speicherfristen. Die mitgelieferten Ergebnisse stammen ausschließlich von lokalen deterministischen Fixtures; es werden keine Aussagen über reale europäische Modelle abgeleitet.

## Euro-Auswirkungen

Der Bericht projiziert beobachtete direkte Verluste und angenommene Prüfkosten auf ein monatliches Volumen. Die Häufigkeit der Störungen im Stresstest ist bewusst hoch. Vor wirtschaftlichen Entscheidungen muss sie durch reale Produktionswahrscheinlichkeiten ersetzt werden. Die Empfehlung lautet `NO-GO` bei beobachteten schädlichen Aktionen oder Überschreiten der Verlustschwelle; ansonsten `REVIEW`, nicht automatische Freigabe.
