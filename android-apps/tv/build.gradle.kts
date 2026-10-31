plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Bouwen buiten iCloud Drive: iCloud maakt anders "… 2"-kopieën van tussenbestanden, en dan faalt de build.
layout.buildDirectory.set(File(System.getProperty("user.home"), ".kantine-apps/build/tv"))

// Let op: de tv-app op de Google TV Streamer is de testversie (assembleDebug), ondertekend met de testsleutel van de Mac
// waarop hij is gebouwd (~/.android/debug.keystore). Een update moet met dezelfde sleutel, anders moet de app eraf en
// is de koppeling en de zoom weg. De testversie wijst gewoon naar de echte site (zie BASIS_URL hieronder).
android {
    namespace = "nl.kantineblauwgeel.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "nl.kantineblauwgeel.tv"
        minSdk = 24
        targetSdk = 34
        versionCode = 4
        versionName = "1.3"
        buildConfigField("String", "BASIS_URL", "\"https://www.kantineblauwgeel.nl\"")
    }

    buildTypes {
        // De testversie kan een ander adres krijgen, bijvoorbeeld een testserver vanuit de emulator:
        // ./gradlew :tv:assembleDebug -PtvBasisUrl=http://10.0.2.2:5056
        debug {
            val basisUrl = (project.findProperty("tvBasisUrl") as String?) ?: "https://www.kantineblauwgeel.nl"
            buildConfigField("String", "BASIS_URL", "\"$basisUrl\"")
        }
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
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}
