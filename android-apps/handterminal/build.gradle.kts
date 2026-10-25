import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// De ondertekensleutel staat bewust buiten de repository (zie README.md). Een update van de app moet met
// dezelfde sleutel ondertekend zijn, anders weigert Android hem over de bestaande installatie heen te zetten.
val ondertekenBestand = File(System.getProperty("user.home"), ".kantine-apps/handterminal-ondertekenen.properties")
val ondertekenen = Properties().apply {
    if (ondertekenBestand.exists()) ondertekenBestand.inputStream().use { load(it) }
}

// Bouwen buiten iCloud Drive: iCloud maakt anders "… 2"-kopieën van tussenbestanden, en dan faalt de build.
layout.buildDirectory.set(File(System.getProperty("user.home"), ".kantine-apps/build/handterminal"))

android {
    namespace = "nl.kantineblauwgeel.handterminal"
    compileSdk = 34

    defaultConfig {
        applicationId = "nl.kantineblauwgeel.handterminal"
        // De Zebra TC51 kwam uit met Android 6.0 (API 23).
        minSdk = 23
        targetSdk = 34
        versionCode = 17
        versionName = "2.14.0"
    }

    signingConfigs {
        if (!ondertekenen.isEmpty) {
            create("release") {
                storeFile = File(ondertekenen.getProperty("storeFile"))
                storePassword = ondertekenen.getProperty("storePassword")
                keyAlias = ondertekenen.getProperty("keyAlias")
                keyPassword = ondertekenen.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
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
        viewBinding = true
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
