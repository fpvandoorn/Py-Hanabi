Some useful commands:

In Py-Hanabi
```
source venv/bin/activate
./hanabi_cli.py solve --class '-2' 0
```
(logs are in `~/.local/state/hanabi-suite/log/`)

In deck-generator
```
go run main.go
```

Interacting with the database
```
sudo -iu postgres
psql
\c hanab-live

SELECT * FROM seeds ORDER BY num;
UPDATE seeds SET feasible = NULL WHERE num = 2342993;
```
(output files are saved in `/var/lib/postgresql`)