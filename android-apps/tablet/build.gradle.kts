plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Bouwen buiten iCloud Drive: iCloud maakt anders "… 2"-kopieën van tussenbestanden, en dan faalt de build.
layout.buildDirectory.set(File(System.getProperty("user.home"), ".kantine-apps/build/tablet"))

android {
    namespace = "nl.kantineblauwgeel.tablet"
    compileSdk = 34

    defaultConfig {
        applicationId = "nl.kantineblauwgeel.tablet"
        minSdk = 24
        targetSdk = 34
        versionCode = 2
        versionName = "2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
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
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
}
