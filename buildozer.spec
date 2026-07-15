[app]
title = EDITH
package.name = edith
package.domain = org.siva.edith

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy==2.3.0,pyjnius,android,cython==0.29.33

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

[buildozer]
log_level = 2
warn_on_root = 1
