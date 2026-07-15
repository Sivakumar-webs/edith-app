import kivy
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.animation import Animation
from kivy.clock import Clock
import threading
from jnius import autoclass, PythonJavaClass, java_method

# ANDROID செட்டிங்
ANDROID = True

# ---- Android native classes (via pyjnius) ----
SpeechRecognizerJ = autoclass('android.speech.SpeechRecognizer')
RecognizerIntent = autoclass('android.speech.RecognizerIntent')
Intent = autoclass('android.content.Intent')
PythonActivity = autoclass('org.kivy.android.PythonActivity')
PackageManager = autoclass('android.content.pm.PackageManager')
ActivityManager = autoclass('android.app.ActivityManager')
Context = autoclass('android.content.Context')
TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
Locale = autoclass('java.util.Locale')

GOOGLE_APP_PACKAGE = "com.google.android.googlequicksearchbox"

# Tamil-script pronunciations of common apps -> real package names.
# Needed because ta-IN speech recognition transcribes "WhatsApp" as
# "வாட்ஸ்அப்" (Tamil script), but the actual installed app label read
# from PackageManager is in English ("whatsapp"). A plain substring
# match between the two scripts will never succeed on its own.
# Add more entries here as you find more mismatches on your device.
APP_ALIASES = {
    "வாட்ஸ்அப்": "com.whatsapp",
    "வாட்சப்": "com.whatsapp",
    "யூடியூப்": "com.google.android.youtube",
    "யூட்யூப்": "com.google.android.youtube",
    "கேலரி": None,       # filled in dynamically below (varies by OEM)
    "செட்டிங்ஸ்": "com.android.settings",
    "கேமரா": None,       # filled in dynamically below (varies by OEM)
}


class UiThreadRunnable(PythonJavaClass):
    """Posts a Python callable onto Looper.getMainLooper() via runOnUiThread."""
    __javainterfaces__ = ['java/lang/Runnable']

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method('()V')
    def run(self):
        try:
            self.fn()
        except Exception as e:
            print(f"[UiThreadRunnable] error: {e}")


def run_on_ui_thread(activity, fn):
    activity.runOnUiThread(UiThreadRunnable(fn))


class TTSInitListener(PythonJavaClass):
    __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']

    def __init__(self, on_init):
        super().__init__()
        self.on_init = on_init

    @java_method('(I)V')
    def onInit(self, status):
        self.on_init(status)


class AndroidTTS:
    """
    Native Android text-to-speech. No internet, no aiohttp, no edge_tts --
    removes the build-risk dependency entirely and speaks instantly through
    the device's own TTS engine.
    """
    def __init__(self):
        self.engine = None
        self.ready = False
        self._pending = []
        self._init_listener = None  # keep a strong ref so pyjnius doesn't GC it
        activity = PythonActivity.mActivity

        def _init():
            self._init_listener = TTSInitListener(self._on_init)
            self.engine = TextToSpeech(activity, self._init_listener)

        run_on_ui_thread(activity, _init)

    def _on_init(self, status):
        if status == TextToSpeech.SUCCESS:
            try:
                self.engine.setLanguage(Locale('ta', 'IN'))
            except Exception as e:
                print(f"TTS language set error (falling back to default): {e}")
            self.ready = True
            for text in self._pending:
                self._speak_now(text)
            self._pending.clear()
        else:
            print("TTS init failed")

    def speak(self, text):
        if self.ready and self.engine:
            self._speak_now(text)
        else:
            self._pending.append(text)

    def _speak_now(self, text):
        activity = PythonActivity.mActivity

        def _do():
            try:
                self.engine.speak(text, TextToSpeech.QUEUE_FLUSH, None, "edith_utt")
            except Exception as e:
                print(f"TTS speak error: {e}")

        run_on_ui_thread(activity, _do)


class AndroidRecognitionListener(PythonJavaClass):
    """Native android.speech.RecognitionListener -- replaces PyAudio/Microphone()."""
    __javainterfaces__ = ['android/speech/RecognitionListener']
    __javacontext__ = 'app'

    def __init__(self, on_result, on_error):
        super().__init__()
        self.on_result = on_result
        self.on_error = on_error

    @java_method('(Landroid/os/Bundle;)V')
    def onReadyForSpeech(self, params):
        pass

    @java_method('()V')
    def onBeginningOfSpeech(self):
        pass

    @java_method('(F)V')
    def onRmsChanged(self, rmsdB):
        pass

    @java_method('([B)V')
    def onBufferReceived(self, buffer):
        pass

    @java_method('()V')
    def onEndOfSpeech(self):
        pass

    @java_method('(I)V')
    def onError(self, error):
        Clock.schedule_once(lambda dt, e=error: self.on_error(e))

    @java_method('(Landroid/os/Bundle;)V')
    def onResults(self, results):
        text = None
        try:
            matches = results.getStringArrayList(SpeechRecognizerJ.RESULTS_RECOGNITION)
            if matches is not None and matches.size() > 0:
                text = matches.get(0)
        except Exception:
            text = None
        Clock.schedule_once(lambda dt, t=text: self.on_result(t))

    @java_method('(Landroid/os/Bundle;)V')
    def onPartialResults(self, partialResults):
        pass

    @java_method('(ILandroid/os/Bundle;)V')
    def onEvent(self, eventType, params):
        pass


# 1. முதலாவது ஸ்கிரீன்
class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.05, 0.05, 0.07, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

        layout = FloatLayout()
        self.btn = Button(
            text="ACTIVATE EDITH", font_size=28, background_normal='',
            background_color=(0, 0, 0, 0), color=(0, 1, 1, 1),
            size_hint=(None, None), size=(300, 80),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )
        anim = Animation(background_color=(0, 0.5, 0.5, 1), duration=1) + Animation(background_color=(0, 0, 0, 0), duration=1)
        anim.repeat = True
        anim.start(self.btn)
        self.btn.bind(on_press=self.activate_edith)
        layout.add_widget(self.btn)
        self.add_widget(layout)

    def _update_rect(self, instance, value):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def activate_edith(self, instance):
        anim = Animation(opacity=0, duration=0.5)
        anim.start(instance)
        anim.bind(on_complete=self.switch_screen)

    def switch_screen(self, *args):
        self.manager.current = 'main_system'
        app = App.get_running_app()
        app.tts.speak("வணக்கம் சிவா பாஸ். எடித் சிஸ்டம் இப்போ முழுமையாக ஆக்டிவேட் செய்யப் பட்டது.")


# 2. இரண்டாவது ஸ்கிரீன்
class MainSystemScreen(Screen):
    def on_enter(self):
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
            ], self._on_permissions_result)
        except Exception as e:
            print(f"Permissions error: {e}")
        # App list is needed for open/close commands even if EDITH mode
        # hasn't been toggled ON yet -- scan it lazily right away.
        if not self.app_list:
            self.scan_apps()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.edith_active = False
        self.app_list = {}
        self.mic_permission_granted = False
        self.recognizer = None
        self.listener = None
        self.is_listening = False

        with self.canvas.before:
            Color(0.05, 0.05, 0.07, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

        layout = FloatLayout()
        self.display_label = Label(text="EDITH READY", size_hint=(1, 0.1), pos_hint={'center_x': 0.5, 'y': 0.5}, color=(1, 1, 1, 1))
        layout.add_widget(self.display_label)

        self.mode_btn = Button(text="EDITH MODE: OFF", size_hint=(None, None), size=(200, 50), pos_hint={'center_x': 0.5, 'y': 0.8})
        self.mode_btn.bind(on_press=self.toggle_mode)
        layout.add_widget(self.mode_btn)

        self.mic_btn = Button(text="MIC", size_hint=(None, None), size=(80, 80), pos_hint={'center_x': 0.5, 'y': 0.1})
        self.mic_btn.bind(on_press=self.highlight_and_listen)
        layout.add_widget(self.mic_btn)
        self.add_widget(layout)

    def _update_rect(self, instance, value):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def _on_permissions_result(self, permissions, grants):
        self.mic_permission_granted = bool(grants) and all(grants)
        if not self.mic_permission_granted:
            Clock.schedule_once(lambda dt: setattr(self.display_label, 'text', "Mic permission NOT granted"))

    def toggle_mode(self, instance):
        self.edith_active = not self.edith_active
        self.mode_btn.text = "EDITH MODE: ON" if self.edith_active else "EDITH MODE: OFF"

    def scan_apps(self):
        """
        Builds {app_name_lowercase: package_name} for EVERY installed app
        with a launcher activity -- WhatsApp, YouTube, Gallery, Settings,
        anything. This is what makes "open <anything>" work generically,
        not just for one hardcoded app.
        """
        try:
            pm = PythonActivity.mActivity.getPackageManager()
            packages = pm.getInstalledPackages(PackageManager.GET_ACTIVITIES)
            self.app_list.clear()
            for i in range(packages.size()):
                package_info = packages.get(i)
                app_label = pm.getApplicationLabel(package_info.applicationInfo)
                self.app_list[str(app_label).lower()] = str(package_info.packageName)
            self.display_label.text = f"Apps found: {len(self.app_list)}"
        except Exception as e:
            self.display_label.text = f"Scan error: {e}"

    # ---- Google App availability / permission check ----
    def _check_google_app_ready(self):
        activity = PythonActivity.mActivity
        pm = activity.getPackageManager()
        try:
            app_info = pm.getApplicationInfo(GOOGLE_APP_PACKAGE, 0)
        except Exception:
            return False, "Google App not installed -- speech recognition unavailable"
        if not app_info.enabled:
            return False, "Google App is disabled -- enable it in Android Settings"
        try:
            Manifest = autoclass('android.Manifest$permission')
            perm_state = pm.checkPermission(Manifest.RECORD_AUDIO, GOOGLE_APP_PACKAGE)
            if perm_state != PackageManager.PERMISSION_GRANTED:
                return False, "Google App lacks mic permission -- enable it in Settings > Apps > Google"
        except Exception:
            pass
        return True, "OK"

    # ---- Microphone / speech recognition (native Android) ----
    def highlight_and_listen(self, instance):
        anim = Animation(size=(90, 90), duration=0.1) + Animation(size=(80, 80), duration=0.1)
        anim.start(instance)
        self.start_listening()

    def start_listening(self):
        if self.is_listening:
            return
        if not self.mic_permission_granted:
            self.display_label.text = "Mic permission not granted yet"
            return

        activity = PythonActivity.mActivity
        if not SpeechRecognizerJ.isRecognitionAvailable(activity):
            self.display_label.text = "No speech recognizer available on this device"
            return

        google_ok, google_msg = self._check_google_app_ready()
        if not google_ok:
            self.display_label.text = google_msg
            return

        self.is_listening = True
        self.display_label.text = "Listening... (Talk now)"

        def _start():
            try:
                if self.recognizer is None:
                    self.listener = AndroidRecognitionListener(
                        on_result=self._handle_result,
                        on_error=self._handle_error,
                    )
                    self.recognizer = SpeechRecognizerJ.createSpeechRecognizer(activity)
                    self.recognizer.setRecognitionListener(self.listener)

                intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ta-IN")
                intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, False)
                self.recognizer.startListening(intent)
            except Exception as e:
                Clock.schedule_once(lambda dt, err=str(e): self._handle_error(f"start_failed: {err}"))

        run_on_ui_thread(activity, _start)

    def _handle_result(self, text):
        self.is_listening = False
        command = (text or "").lower()
        self.display_label.text = f"You: {command}" if command else "Could not understand."
        if command:
            self.process_command(command)

    def _handle_error(self, error_code):
        self.is_listening = False
        self.display_label.text = f"Mic Error: {error_code}"

    # ---- Location speech (kept as-is: hardcoded location, per original) ----
    def speak_location(self, location_text):
        text = f"சிவா பாஸ், நீங்கள் தற்போது {location_text} பகுதியில் இருக்கிறீர்கள்."
        App.get_running_app().tts.speak(text)

    # ---- App launch / close via real Android APIs (works for ANY app) ----
    def launch_app(self, package_name):
        try:
            activity = PythonActivity.mActivity
            pm = activity.getPackageManager()
            launch_intent = pm.getLaunchIntentForPackage(package_name)
            if launch_intent:
                activity.startActivity(launch_intent)
                self.display_label.text = f"Launching: {package_name}"
            else:
                self.display_label.text = "Intent not found!"
        except Exception as e:
            self.display_label.text = f"Launch error: {e}"

    def close_app(self, package_name):
        """
        NOTE: a normal third-party app cannot force-stop another app the
        way `am force-stop` (adb/system-level) can. The closest legal API
        is killBackgroundProcesses, which only affects the target app if
        it is currently in the background -- Android does not allow any
        regular app to forcibly kill another app's foreground process.
        This is a platform security restriction, not a bug here.
        """
        try:
            activity = PythonActivity.mActivity
            am = activity.getSystemService(Context.ACTIVITY_SERVICE)
            am.killBackgroundProcesses(package_name)
            self.display_label.text = f"Requested stop: {package_name}"
        except Exception as e:
            self.display_label.text = f"Close error: {e}"

    def resolve_app_name(self, app_name):
        """
        Resolves a spoken app name to a package name. Checks the Tamil
        alias map first (handles script mismatch between ta-IN speech
        recognition output and English PackageManager labels), then
        falls back to a plain substring match against installed apps.
        """
        app_name = app_name.strip()
        if not app_name:
            return None

        alias_pkg = APP_ALIASES.get(app_name)
        if alias_pkg:
            # Confirm it's actually installed on this device before using it.
            if alias_pkg in self.app_list.values():
                return alias_pkg
            return None

        for name, pkg in self.app_list.items():
            if app_name in name:
                return pkg
        return None

    def process_command(self, command):
        location_keywords = ["எங்க இருக்கேன்", "லொகேஷன்", "எங்க இருக்க", "where am i",
                              "my location", "track my location", "இடத்தோட பேர் என்ன", "current location"]

        if any(keyword in command for keyword in location_keywords):
            if self.edith_active:
                threading.Thread(target=self.speak_location, args=("மதுரை",), daemon=True).start()

        elif "ஓபன் பண்ணு" in command or "திற" in command or "open" in command:
            app_name = (command.replace("ஓபன் பண்ணு", "")
                                .replace("திற", "")
                                .replace("open", "")
                                .strip())
            if not self.app_list:
                self.scan_apps()
            resolved_pkg = self.resolve_app_name(app_name)
            if resolved_pkg:
                self.launch_app(resolved_pkg)
            else:
                self.display_label.text = "ஆப் கிடைக்கவில்லை பாஸ்!"

        elif "க்ளோஸ் பண்ணு" in command or "மூடு" in command or "close" in command:
            app_name = (command.replace("க்ளோஸ் பண்ணு", "")
                                .replace("மூடு", "")
                                .replace("close", "")
                                .strip())
            resolved_pkg = self.resolve_app_name(app_name)
            if resolved_pkg:
                self.close_app(resolved_pkg)

        elif "ஸ்லீப் மோடு" in command or "sleep mode" in command:
            self.edith_active = False
            self.mode_btn.text = "EDITH MODE: OFF"

    def on_leave(self, *args):
        if self.recognizer is not None:
            try:
                self.recognizer.destroy()
            except Exception:
                pass
            self.recognizer = None
            self.listener = None
            self.is_listening = False


class EdithApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(WelcomeScreen(name='welcome'))
        sm.add_widget(MainSystemScreen(name='main_system'))
        return sm

    def on_start(self):
        # Native TTS engine, shared across the whole app.
        self.tts = AndroidTTS()


if __name__ == "__main__":
    EdithApp().run()