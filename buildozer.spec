[app]
title = EDITH
package.name = edith
package.domain = org.siva.edith

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy,pyjnius,android

orientation = portrait
fullscreen = 0

# icon.filename removed -- only add this back if you place a real
# icon.png file in this same folder.
# icon.filename = %(source.dir)s/icon.png

# ---- Permissions ----
android.permissions = RECORD_AUDIO,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,KILL_BACKGROUND_PROCESSES,QUERY_ALL_PACKAGES

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.accept_sdk_license = True

android.archs = arm64-v8a, armeabi-v7a

android.wakelock = False

# ---- Pin python-for-android to the last stable, officially released
# version (Jan 2024). This predates Python 3.14 entirely, which avoids a
# currently OPEN, unresolved upstream bug where p4a's newest code tries
# to build against Python 3.14 and breaks Kivy's compiled C extensions
# (see: github.com/kivy/python-for-android issue #3274). Pinning here is
# what actually fixes the build -- not a workaround in our own code.
p4a.branch = master
p4a.commit = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
