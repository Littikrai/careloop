from django.core.management.base import BaseCommand

from businesses.document_knowledge import recover_document_index_attempts


class Command(BaseCommand):
    help = "Mark abandoned document indexing attempts as interrupted."

    def add_arguments(self, parser):
        parser.add_argument(
            "--startup",
            action="store_true",
            help="Mark every running attempt interrupted before a restarted app begins serving requests.",
        )

    def handle(self, *args, **options):
        recovered = recover_document_index_attempts(at_startup=options["startup"])
        self.stdout.write(f"Interrupted {recovered} document indexing attempt(s).")
