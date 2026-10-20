plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "nl.kantineblauwgeel.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "nl.kantineblauwgeel.tv"
        minSdk = 24
        targetSdk = 34
        versionCode = 2
        versionName = "1.1"
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
