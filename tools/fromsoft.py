# SPDX-License-Identifier: GPL-2.0-or-later
"""FromSoftware containers as Bloodborne 1.09 ships them: DCX (DFLT, zlib) and BND4.

The PC features rewrite a few of the player's own game files at start (the Hunter's Dream
layout, the Altar of Despair's talk script, event scripts, menu assets); these read and write
the containers around them. Formats as documented by SoulsFormats and droogie's bbhost.
"""
import struct
import zlib

# The DCX header Bloodborne's DFLT files use: big-endian offsets, compression level 9.
_DCX_HEADER = struct.Struct('>4sIIIII4sII4s4sIB3xIIII4sI')


class FormatError(ValueError):
    pass


def dcx_decompress(data):
    if data[:4] != b'DCX\0':
        raise FormatError('not a DCX file')
    if data[0x28:0x2c] != b'DFLT':
        raise FormatError(f'unsupported DCX compression {data[0x28:0x2c]!r}')
    size, packed = struct.unpack_from('>II', data, 0x1c)
    try:
        start = data.index(b'DCA\0', 0x2c) + 8
    except ValueError:
        raise FormatError('DCX header has no DCA block') from None
    # A damaged file (a cut-short copy, a repack with a wrong header) is a format error, so the
    # feature reading it turns itself off rather than stopping the game.
    if len(data) - start < packed:
        raise FormatError(f'DCX file is truncated: its header says {packed} bytes of data, '
                          f'the file has {len(data) - start}')
    try:
        out = zlib.decompress(data[start:start + packed])
    except zlib.error as error:
        raise FormatError(f'DCX data is damaged ({error})') from None
    if len(out) != size:
        raise FormatError('DCX size does not match its header')
    return out


def dcx_compress(data, template=None):
    """DFLT DCX of `data`. With `template` (the file being replaced) its header is kept and only
    the sizes change, so the result differs from the original only where the content does."""
    packed = zlib.compress(data, 9)
    if template is not None:
        if template[:4] != b'DCX\0' or template[0x28:0x2c] != b'DFLT':
            raise FormatError('template is not a DFLT DCX file')
        start = template.index(b'DCA\0', 0x2c) + 8
        header = bytearray(template[:start])
        struct.pack_into('>II', header, 0x1c, len(data), len(packed))
        return bytes(header) + packed
    header = _DCX_HEADER.pack(b'DCX\0', 0x10000, 0x18, 0x24, 0x44, 0x4c, b'DCS\0', len(data), len(packed),
                              b'DCP\0', b'DFLT', 0x20, 9, 0, 0, 0, 0x10100, b'DCA\0', 8)
    return header + packed


class Bnd4:
    """A BND4 archive whose files can be replaced. Everything but the files' data, their sizes
    and their offsets is kept byte for byte (names, ids, flags, hash table, header)."""

    # File header layouts by size: (offset of the compressed size, of the uncompressed size or
    # None, of the data offset).
    _LAYOUTS = {0x24: (0x08, 0x10, 0x18), 0x20: (0x08, 0x10, 0x18), 0x18: (0x08, None, 0x10)}

    def __init__(self, data):
        if data[:4] != b'BND4':
            raise FormatError('not a BND4 archive')
        if data[8]:
            raise FormatError('big-endian BND4 is unsupported')
        count, = struct.unpack_from('<i', data, 0x0c)
        self.header_size, = struct.unpack_from('<q', data, 0x20)
        if self.header_size not in self._LAYOUTS:
            raise FormatError(f'unsupported BND4 file header size {self.header_size:#x}')
        self.unicode = bool(data[0x30])
        self._data = data
        self.names, self.files, self.ids, offsets = [], [], [], []
        size_at, _, offset_at = self._LAYOUTS[self.header_size]
        for i in range(count):
            at = 0x40 + i * self.header_size
            size, = struct.unpack_from('<q', data, at + size_at)
            offset, = struct.unpack_from('<I', data, at + offset_at)
            name_at, = struct.unpack_from('<I', data, at + self.header_size - 4)
            self.names.append(self._name(name_at))
            # The file id follows the data offset in the 0x24-byte headers (None without one).
            self.ids.append(struct.unpack_from('<i', data, at + offset_at + 4)[0]
                            if self.header_size == 0x24 else None)
            self.files.append(bytes(data[offset:offset + size]))
            offsets.append(offset)
        self._offsets = offsets
        self._end = max((o + len(f) for o, f in zip(offsets, self.files)), default=len(data))
        self._start = min(offsets) if offsets else len(data)
        # The archive's data alignment: the largest power of two (up to 0x10) every offset keeps.
        self.align = 0x10
        while self.align > 1 and any(o % self.align for o in offsets):
            self.align //= 2

    def _name(self, at):
        data = self._data
        if self.unicode:
            end = at
            while data[end:end + 2] != b'\0\0':
                end += 2
            return data[at:end].decode('utf-16-le')
        return data[at:data.index(b'\0', at)].decode('shift_jis')

    def index(self, name):
        """Index of the file whose path ends with `name` (case-insensitive)."""
        wanted = name.replace('/', '\\').casefold()
        matches = [i for i, n in enumerate(self.names) if n.replace('/', '\\').casefold().endswith(wanted)]
        if len(matches) != 1:
            raise FormatError(f'{name}: {len(matches)} matching files in the archive')
        return matches[0]

    def to_bytes(self):
        prefix = bytearray(self._data[:self._start])
        size_at, raw_at, offset_at = self._LAYOUTS[self.header_size]
        body = bytearray()
        # Files keep their original order in the data area.
        for i in sorted(range(len(self.files)), key=lambda i: self._offsets[i]):
            while (self._start + len(body)) % self.align:
                body.append(0)
            at = 0x40 + i * self.header_size
            struct.pack_into('<q', prefix, at + size_at, len(self.files[i]))
            if raw_at is not None:
                struct.pack_into('<q', prefix, at + raw_at, len(self.files[i]))
            struct.pack_into('<I', prefix, at + offset_at, self._start + len(body))
            body += self.files[i]
        tail = self._data[self._end:]
        return bytes(prefix + body + tail)
