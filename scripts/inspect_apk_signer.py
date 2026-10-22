"""Inspect Android APK Signing Block V2/V3 certificates without needing Java.

Pure stdlib read-only helper; does not extract or reveal private keys.
"""
import hashlib
import struct
import sys
from pathlib import Path


MAGIC=b"APK Sig Block 42"
IDS={0x7109871A:"APK Signature Scheme v2",0xF05368C0:"APK Signature Scheme v3",
     0x1B93AD61:"APK Signature Scheme v3.1"}


def lp(buf:bytes,at:int=0):
    if at+4>len(buf): raise ValueError("Missing length prefix")
    n=struct.unpack_from("<I",buf,at)[0]
    end=at+4+n
    if end>len(buf): raise ValueError("Truncated length-prefixed data")
    return buf[at+4:end],end


def inspect(path:Path)->None:
    raw=path.read_bytes()
    eocd=raw.rfind(bytes([0x50,0x4B,0x05,0x06]),max(0,len(raw)-65557))
    if eocd<0: raise ValueError("ZIP end of central directory missing")
    cd=struct.unpack_from("<I",raw,eocd+16)[0]
    footer=cd-24
    if footer<0 or raw[footer+8:cd]!=MAGIC:
        raise ValueError("APK signing block missing")
    size=struct.unpack_from("<Q",raw,footer)[0]
    start=cd-size-8
    if struct.unpack_from("<Q",raw,start)[0]!=size:
        raise ValueError("APK signing block size mismatch")
    print(f"{path.name}: {len(raw)} bytes; APK SHA-256 {hashlib.sha256(raw).hexdigest()}")
    at=start+8
    found=False
    while at<footer:
        length=struct.unpack_from("<Q",raw,at)[0]
        block_id=struct.unpack_from("<I",raw,at+8)[0]
        block=raw[at+12:at+8+length]
        at+=length+8
        if block_id not in IDS:continue
        signer_list,_=lp(block)
        signer,_=lp(signer_list)
        signed_data,_=lp(signer)
        _,o=lp(signed_data)
        certificates,_=lp(signed_data,o)
        certificate,_=lp(certificates)
        print(f" {IDS[block_id]} signer certificate SHA-256: {hashlib.sha256(certificate).hexdigest().upper()}")
        found=True
    if not found: raise ValueError("No recognized V2/V3 signer block")


if __name__=="__main__":
    for filename in sys.argv[1:]:inspect(Path(filename))
