# TheSoldMyEmail-DomainList

TheSoldMyEmail  DomainList - Script zum auslesen der offenen "Issues" von https://github.com/svemailproject/TheySoldMyEmail/issues
Zweck ist es, eine CSV zu erstellen, die die Domains auflistet welche da aufgeführt sind um diese dann weiter zu verarbeiten, bzw Logins zu erstellen und diese dann zu verfolgen.

export_issues_domains.py  - ruft ALLE Issues numerisch auf und speichert folgende Daten in der "issues-latest.csv":
Issue Number - Issue Url - Title - Domain - Domain Source - Author - Created_at
Sollte die issues-latest.csv bereits vorhanden sein, wird die alte ersetzt mit Timecode

merge.py - ruft ALLE Daten aus der issues-latest.csv ab und speichert diese in der "issues-db.csv" ohne dabei Daten zu überschreiben. 
