# Sessionstranskripten ligger i Google Drive

Kanonisk plats: `~/gdrive/SESSIONSTRANSKRIPT_<datum>.md`
Det är en rclone-FUSE-montering av Drive-roten — filen du redigerar där ÄR filen i Drive.

- montering: `systemctl --user status rclone-gdrive`
- om monteringen är nere: skriv lokalt i `docs/` och kör `~/bin/transkript_push.sh`
- rclone-remote: `gdrive:` (scope=drive, token i `~/.config/rclone/rclone.conf`, chmod 600)

Ingen kopia sparas i repot, för att undvika två versioner som glider isär.
