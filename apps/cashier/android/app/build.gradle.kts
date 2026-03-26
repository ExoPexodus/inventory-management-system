import com.flutter.gradle.tasks.FlutterTask

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.inventory.platform.cashier"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.inventory.platform.cashier"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    // Resolved from :app project dir (android/app); two levels up = Flutter package root.
    source = "../.."
}

// Flutter passes lib\main.dart on Windows; normalize after the plugin sets targetPath.
afterEvaluate {
    tasks.withType<FlutterTask>().configureEach {
        val tp = targetPath
        if (tp != null) {
            // Avoid lib//main.dart when the path already used \ or mixed separators.
            targetPath = tp.replace('\\', '/').replace(Regex("/+"), "/")
        }
    }
}
