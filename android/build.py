"""手工打包 APK（不依赖 Gradle）：aapt2 → javac → d8 → zipalign → apksigner。

用法： python build.py
产物： dist/JMComicClient.apk
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
PACKAGE = "com.jmcomic.app"
MIN_SDK = 29
TARGET_SDK = 35
VERSION_NAME = "1.0.1"

JAVA_HOME = Path("C:/Program Files/Java/jdk-17")


def find_sdk() -> Path:
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(env)
        if value and Path(value).is_dir():
            return Path(value)
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"
    if default.is_dir():
        return default
    raise SystemExit("找不到 Android SDK，请设置 ANDROID_HOME")


def newest(path: Path) -> Path:
    items = [p for p in path.iterdir() if p.is_dir()]
    if not items:
        raise SystemExit(f"目录为空: {path}")
    return sorted(items, key=lambda p: p.name)[-1]


def run(cmd, **kwargs):
    print("$", " ".join(str(c) for c in cmd))
    result = subprocess.run([str(c) for c in cmd], **kwargs)
    if result.returncode != 0:
        raise SystemExit(f"命令失败({result.returncode})")


def main() -> int:
    sdk = find_sdk()
    build_tools = newest(sdk / "build-tools")
    android_jar = newest(sdk / "platforms") / "android.jar"
    aapt2 = build_tools / "aapt2.exe"
    d8 = build_tools / "d8.bat"
    zipalign = build_tools / "zipalign.exe"
    apksigner = build_tools / "apksigner.bat"

    javac = JAVA_HOME / "bin" / "javac.exe"
    jar = JAVA_HOME / "bin" / "jar.exe"
    keytool = JAVA_HOME / "bin" / "keytool.exe"
    if not javac.exists():
        javac = Path(shutil.which("javac"))
        jar = Path(shutil.which("jar"))
        keytool = Path(shutil.which("keytool"))

    print(f"SDK      : {sdk}")
    print(f"build-tools: {build_tools.name}")
    print(f"android.jar: {android_jar}")

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    DIST.mkdir(exist_ok=True)

    # 1) 资源编译
    run([aapt2, "compile", "--dir", APP / "res", "-o", BUILD / "res.zip"])

    # 2) 链接资源 + manifest + assets
    gen = BUILD / "gen"
    gen.mkdir()
    base_apk = BUILD / "base.apk"
    run([
        aapt2, "link", "-o", base_apk,
        "-I", android_jar,
        "--manifest", APP / "AndroidManifest.xml",
        "-A", APP / "assets",
        "--java", gen,
        "--min-sdk-version", str(MIN_SDK),
        "--target-sdk-version", str(TARGET_SDK),
        "--version-code", "2",
        "--version-name", VERSION_NAME,
        "--auto-add-overlay",
        BUILD / "res.zip",
    ])

    # 3) 编译 Java
    sources = sorted(str(p) for p in (APP / "src").rglob("*.java"))
    r_java = sorted(str(p) for p in gen.rglob("R.java"))
    classes = BUILD / "classes"
    classes.mkdir()
    run([javac, "--release", "11", "-encoding", "UTF-8", "-nowarn",
         "-cp", android_jar, "-d", classes] + r_java + sources)

    # 4) 转 dex
    classes_jar = BUILD / "classes.jar"
    run([jar, "cf", classes_jar, "-C", classes, "."])
    dex_dir = BUILD / "dex"
    dex_dir.mkdir()
    run([d8, "--lib", android_jar, "--min-api", str(MIN_SDK), "--release",
         "--output", dex_dir, classes_jar])

    # 5) 把 classes.dex 塞进 apk
    with zipfile.ZipFile(base_apk, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex_dir / "classes.dex", "classes.dex")

    # 6) 对齐
    aligned = BUILD / "aligned.apk"
    run([zipalign, "-f", "-p", "4", base_apk, aligned])

    # 7) 签名
    keystore = ROOT / "keystore" / "jmcomic.jks"
    if not keystore.exists():
        keystore.parent.mkdir(exist_ok=True)
        run([keytool, "-genkeypair", "-keystore", keystore, "-storepass", "jmcomic123",
             "-keypass", "jmcomic123", "-alias", "jmcomic", "-keyalg", "RSA",
             "-keysize", "2048", "-validity", "10000",
             "-dname", "CN=JMComic, OU=App, O=JM, L=Shanghai, C=CN"])

    out = DIST / "JMComicClient.apk"
    if out.exists():
        out.unlink()
    run([apksigner, "sign", "--ks", keystore, "--ks-pass", "pass:jmcomic123",
         "--key-pass", "pass:jmcomic123", "--out", out, aligned])
    run([apksigner, "verify", "--print-certs", out])

    size = out.stat().st_size / 1024 / 1024
    print(f"\n完成：{out}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
