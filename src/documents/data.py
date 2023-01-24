import dataclasses
import datetime
import enum
import hashlib
import tempfile
from functools import cached_property
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

import dateutil
import magic
import pathvalidate
from django.conf import settings


@dataclasses.dataclass
class DocumentOverrides:
    """
    Manages overrides for document fields which normally would
    be set from content or matching.  All fields default to None,
    meaning no override is happening
    """

    filename: Optional[str] = None
    title: Optional[str] = None
    correspondent_id: Optional[int] = None
    document_type_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    created: Optional[datetime.datetime] = None
    asn: Optional[int] = None

    def as_dict(self) -> Dict:
        return {
            "filename": self.filename,
            "title": self.title,
            "correspondent_id": self.correspondent_id,
            "document_type_id": self.document_type_id,
            "archive_serial_num": self.asn,
            "tag_ids": self.tag_ids,
            "created": self.created.isoformat() if self.created else None,
        }

    @staticmethod
    def from_dict(data: Dict) -> "DocumentOverrides":
        return DocumentOverrides(
            data["filename"],
            data["title"],
            data["correspondent_id"],
            data["document_type_id"],
            data["tag_ids"],
            dateutil.parser.isoparse(data["created"]) if data["created"] else None,
            data["archive_serial_num"],
        )


class DocumentSource(enum.IntEnum):
    """
    The source of an incoming document.  May have other uses in the future
    """

    ConsumeFolder = enum.auto()
    ApiUpload = enum.auto()
    MailFetch = enum.auto()


@dataclasses.dataclass
class ConsumeDocument:
    """
    Encapsulates an incoming document, either from consume folder, API upload
    or mail fetching and certain useful operations on it.
    """

    source: DocumentSource
    original_file: Path
    working_file: Optional[Path] = None
    mime_type: Optional[str] = None

    def __post_init__(self):
        """
        After a dataclass is initialized, this is called to finalize some data
        1. Make sure the original path is an absolute, fully qualified path
        2. If not already set, get the mime type of the file
        3. If the document is from the consume folder, create a shadow copy
           of the file in scratch to work with
        """
        # Always fully qualify the path first thing
        self.original_file = Path(self.original_file).resolve()

        # Get the file type once at init, not when from serialized
        if self.mime_type is None:
            self.mime_type = magic.from_file(self.original_file, mime=True)

        # Copy the original file into a temporary file for work to happen,
        # while ensuring modifications do not trigger a second consume
        # Only do this is the document is from the consume
        # and if the file hasn't already been provided
        if self.source == DocumentSource.ConsumeFolder and self.working_file is None:
            self.working_file = (
                Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
                / Path(
                    pathvalidate.sanitize_filename(self.original_file.name),
                )
            ).resolve()
            self.working_file.write_bytes(self.original_file.read_bytes())

    @cached_property
    def checksum(self) -> str:
        """
        Returns the MD5 hash hex digest of the file
        """
        return hashlib.md5(self.path.read_bytes()).hexdigest()

    @cached_property
    def path(self) -> Path:
        """
        Returns the path for outside sources to perform actions against.  This
        is like the "public" file
        """
        if self.source == DocumentSource.ConsumeFolder:
            return self.working_file
        return self.original_file

    def as_dict(self) -> Dict:
        """
        Serializes the dataclass into a dictionary of only basic types like
        strings and ints
        """
        return {
            "source": int(self.source),
            "original_file": str(self.original_file),
            "working_file": str(self.working_file) if self.working_file else None,
            "mime_type": self.mime_type,
        }

    @staticmethod
    def from_dict(data: Dict) -> "ConsumeDocument":
        """
        Given a serialized dataclass, returns the
        """
        doc = ConsumeDocument(
            DocumentSource(data["source"]),
            Path(data["original_file"]),
            # This may be none if the original file already resides in the scratch
            Path(data["working_file"]) if data["working_file"] else None,
            # The mime type is already determined in this case,
            # don't gather a second time
            data["mime_type"],
        )
        return doc
