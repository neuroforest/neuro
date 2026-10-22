"""
The blob key convention and the canonical mime → extension table.

A blob is content identified by its sha256; where it sits in an object store
is implicit in the prefix that contains it and its nid, never stored and never
spelled with an extension:

    object leaf   <prefix>/<blob-nid>
    member leaf   <prefix>/<subject-nid>/<member>

The prefix of an object-leaf is the lowercase leaf class of the blob (``Image``
→ ``image``); a member-leaf prefix is named after the pipeline step and its
leaves draw on a closed vocabulary (``reads/<nid>/R1.fastq.gz``). Anything that
fits neither scheme is an explicit ``BlobObject`` carrying its own ``key``.

The extension is information about the bytes, recorded on the blob from the
mime type through one table so the same content never gets two spellings
(``jpg``/``jpeg``).
"""

import hashlib
import re
import uuid

LEAF_OBJECT = "object"
LEAF_MEMBER = "member"

# One canonical extension per mime type - the only place the choice is made.
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/tiff": "tif",
    "image/bmp": "bmp",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/svg+xml": "svg",
    "image/x-icon": "ico",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/x-matroska": "mkv",
    "video/webm": "webm",
    "video/mpeg": "mpg",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
    "audio/mp4": "m4a",
    "application/pdf": "pdf",
    "application/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/zip": "zip",
    "application/gzip": "gz",
    "application/x-gzip": "gz",
    "application/x-tar": "tar",
    "application/x-bzip2": "bz2",
    "application/x-xz": "xz",
    "application/vnd.google-earth.kml+xml": "kml",
    "application/vnd.google-earth.kmz": "kmz",
    "application/gpx+xml": "gpx",
    "application/octet-stream": "bin",
    "text/plain": "txt",
    "text/csv": "csv",
    "text/tab-separated-values": "tsv",
    "text/html": "html",
    "text/markdown": "md",
    "text/x-python": "py",
    "application/javascript": "js",
    "text/javascript": "js",
    "text/css": "css",
}

# Extensions a file may carry that are not the canonical spelling of its mime.
_ALIASES = {
    "jpeg": "jpg",
    "jpe": "jpg",
    "thm": "jpg",
    "tiff": "tif",
    "htm": "html",
    "mpeg": "mpg",
    "lrv": "mp4",
}

_HEX = re.compile(r"[0-9a-f]{64}")


def extension_for(mime_type):
    """
    Return the canonical extension for a mime type, or ``None`` when the
    table does not know it. A ``;charset=…`` parameter is ignored.
    """
    if not mime_type:
        return None
    base = mime_type.split(";", 1)[0].strip().lower()
    return EXTENSIONS.get(base)


def canonical_extension(extension):
    """
    Normalise an extension as found on a filename - leading dot and case
    stripped, aliases folded (``jpeg`` → ``jpg``). Unknown spellings pass
    through lowercased.
    """
    if not extension:
        return None
    ext = extension.lower().lstrip(".")
    return _ALIASES.get(ext, ext)


def blob_key(prefix, nid, *, leaf_kind=LEAF_OBJECT, subject_nid=None, member=None):
    """
    Build the implicit object key of a blob under a prefix.

    :param prefix: the prefix name, or ``bucket/prefix`` - used verbatim.
    :param nid: the blob's nid (object leaf) - ignored for a member leaf.
    :param leaf_kind: ``"object"`` or ``"member"``, the prefix's declared kind.
    :param subject_nid: the owning record's nid, member leaf only.
    :param member: the member name, member leaf only.
    :raises ValueError: when the leaf kind has no implicit key - that object
        needs an explicit ``BlobObject``.
    """
    prefix = prefix.strip("/")
    if leaf_kind == LEAF_OBJECT:
        if not nid:
            raise ValueError("object leaf needs the blob's nid")
        return f"{prefix}/{nid}"
    if leaf_kind == LEAF_MEMBER:
        if not (subject_nid and member):
            raise ValueError("member leaf needs the subject's nid and the member name")
        return f"{prefix}/{subject_nid}/{member}"
    raise ValueError(f"no implicit key for leaf_kind {leaf_kind!r}")


def implicit_nid(key, prefix):
    """
    Return the blob nid an object-leaf key encodes, or ``None`` when the key
    is not of the implicit form ``<prefix>/<uuid4>`` - the collector then
    mints a ``BlobObject`` for it.
    """
    prefix = prefix.strip("/") + "/"
    if not key.startswith(prefix):
        return None
    leaf = key[len(prefix):]
    if "/" in leaf or "." in leaf:
        return None
    try:
        parsed = uuid.UUID(leaf)
    except ValueError:
        return None
    if parsed.version != 4 or str(parsed) != leaf:
        return None
    return leaf


def is_sha256(value):
    """True for a lowercase 64-hex sha256 digest."""
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def sha256_of(path, chunk_size=1 << 20):
    """Stream a file and return its lowercase hex sha256."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
