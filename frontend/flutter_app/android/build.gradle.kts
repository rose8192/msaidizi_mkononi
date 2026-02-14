allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

subprojects {
    afterEvaluate {
        if (project.hasProperty("android")) {
            val android = project.extensions.getByName("android")
            if (android is com.android.build.gradle.BaseExtension) {
                if (android.namespace == null) {
                    android.namespace = "com.msaidizi_mkononi.${project.name.replace("-", "_")}"
                }
                android.compileSdkVersion(36)
                
                // Force configuration for all subprojects
                android.defaultConfig {
                    minSdk = 24
                    targetSdk = 36
                }
            }
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
