plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.benessere.app"
    compileSdk = 36

    defaultConfig {
        // Canary is installable beside the already-signed Benessere app.
        // It never upgrades or alters the existing installation.
        applicationId = if (project.hasProperty("benessereCanary"))
            "com.benessere.app.canary" else "com.benessere.app"
        manifestPlaceholders["benessereAppLabel"] =
            if (project.hasProperty("benessereCanary")) "Benessere TEST" else "Benessere"
        minSdk = 28
        targetSdk = 34
        versionCode = 9
        versionName = "0.2.5"
    }

    // L'APK di aggiornamento deve usare la firma dell'app già installata.
    // GitHub Actions fornisce il percorso della keystore originale come
    // variabile d'ambiente, senza committare o esporre la chiave privata.
    signingConfigs {
        getByName("debug") {
            System.getenv("BENESSERE_SIGNING_KEYSTORE_PATH")
                ?.takeIf { it.isNotBlank() }
                ?.let { path ->
                    storeFile = file(path)
                    storePassword = "android"
                    keyAlias = "androiddebugkey"
                    keyPassword = "android"
                }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.health.connect)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.androidx.ui.tooling)
}

// Copia l'APK nella cartella servita in LAN da `python -m http.server 8001 --directory dist`.
val debugVersionName = android.defaultConfig.versionName ?: "dev"
tasks.register<Copy>("exportDebugApk") {
    dependsOn("assembleDebug")
    from(layout.buildDirectory.file("outputs/apk/debug/app-debug.apk"))
    into(rootProject.layout.projectDirectory.dir("../dist"))
    rename { "benessere-v${debugVersionName}-debug.apk" }
}
