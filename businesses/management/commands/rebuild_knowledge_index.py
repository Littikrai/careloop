from django.core.management.base import BaseCommand, CommandError

from businesses.index_rebuild import pending_backup_dir, rebuild_index_if_needed


class Command(BaseCommand):
    help = "Rebuild every published Q&A and Document vector if the embedding or chunking signature changed."

    def handle(self, *args, **options):
        try:
            rebuilt, backup_dir = rebuild_index_if_needed()
        except Exception as error:
            backup_dir = pending_backup_dir()
            backup_message = f" Previous data backup: {backup_dir}." if backup_dir else ""
            raise CommandError(
                f"Knowledge index rebuild failed; the application will not start: {error}.{backup_message}"
            ) from error
        if not rebuilt:
            self.stdout.write("Knowledge index signature matches the configured model and chunker; no rebuild needed.")
        elif backup_dir:
            self.stdout.write(self.style.SUCCESS(f"Knowledge index rebuilt. Previous data backup: {backup_dir}"))
        else:
            self.stdout.write(self.style.SUCCESS("Knowledge index signature initialized; no published content to rebuild."))
