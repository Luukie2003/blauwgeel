plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Bouwen buiten iCloud Drive: iCloud maakt anders "… 2"-kopieën van tussenbestanden, en dan faalt de build.
layout.buildDirectory.set(File(System.getProperty("user.home"), ".kantine-apps/build/tablet"))

// Kantine Beheer 3.0 bouwt op de schermen van de handterminal-app: die code en zijn resources komen hier mee in
// (sourceSets), zonder dat er in de handterminal-module iets verandert. Wat alleen op de handterminal hoort (de
// looplijsten, de scanner), regelt App.kt daar. Daarom heeft deze module dezelfde namespace (R, BuildConfig en de
// viewbindings van de gedeelde code), maar een eigen applicationId: de tablet blijft dezelfde app, die over de oude heen
// installeert (een debug-APK van deze Mac, met dezelfde sleutel als de tv-app).
val handterminal = "../handterminal/src/main"

android {
    namespace = "nl.kantineblauwgeel.handterminal"
    compileSdk = 34

    defaultConfig {
        applicationId = "nl.kantineblauwgeel.tablet"
        minSdk = 24
        targetSdk = 34
        versionCode = 4
        versionName = "3.1"
    }

    sourceSets {
        getByName("main") {
            java.srcDirs("src/main/java", "$handterminal/java")
            res.srcDirs("$handterminal/res", "src/main/res")
            assets.srcDirs("$handterminal/assets")
        }
        // Teksten die op de tablet anders zijn dan op de handterminal (de naam van de app, ...): een build-type-map gaat
        // vóór main, dus deze winnen van de handterminal-resources met dezelfde naam.
        getByName("debug") { res.srcDirs("src/tablet/res") }
        getByName("release") { res.srcDirs("src/tablet/res") }
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
        buildConfig = true
    }
}

dependencies {
    // Die van de handterminal-app (dezelfde versies), en Material voor de eigen tv-schermen van de tablet.
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.google.android.material:material:1.12.0")
}
