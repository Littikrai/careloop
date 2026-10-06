from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from businesses.index_rebuild import restore_index_backup


class Command(BaseCommand):
    help = "Restore the SQLite database and local Qdrant files from a knowledge-index rebuild backup."

    def add_arguments(self, parser):
        parser.add_argument("backup_dir", type=Path)

    def handle(self, *args, **options):
        backup_dir = options["backup_dir"]
        try:
            restore_index_backup(backup_dir)
        except Exception as error:
            raise CommandError(f"Could not restore knowledge-index backup: {error}") from error
        self.stdout.write(self.style.SUCCESS(f"Restored application data from {backup_dir}"))
