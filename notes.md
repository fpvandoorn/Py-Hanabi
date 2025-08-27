Some useful commands:

In Py-Hanabi
```
source venv/bin/activate
./hanabi_cli.py solve --class '-2' 0
```


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