# 04: JSON Q&A import

**Status:** done

The admin can select a business and upload a UTF-8 JSON Q&A array. All records are validated before database writes. Exact duplicates are skipped; conflicting answers reject the complete import. Successful rows are drafts for normal review and publishing.
