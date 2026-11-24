// Jenkinsfile - multi-stage CI for BOOT Flasher (bootloader-gui).
//
//   Checkout -> Setup -> Check -> Tests -> Package -> Release (tags) -> Archive
//
// Package builds dist/<repo>-<version>.tar.gz (GUI bundle, manifest.json,
// SHA256SUMS) on every run.  Release runs only for a tag v<version> and
// publishes dist/ as a GitHub release with the Jenkins secret-text credential
// github-release-token.  To release: bump the version in gui/__init__.py,
// push, then push the tag (git tag v1.0.0 && git push origin v1.0.0).
//
// Pure Python; the agent needs python3 (>= 3.10), git and network access for
// PyPI.  The GUI never starts for real: the tests run headless with
// QT_QPA_PLATFORM=offscreen, and the packaging step needs PyInstaller.

pipeline {
    agent any

    options {
        skipDefaultCheckout()
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    parameters {
        booleanParam(name: 'PACKAGE', defaultValue: false, description: 'Build the PyInstaller bundle; always done for a release tag')
    }

    environment {
        VENV              = '.venv'
        QT_QPA_PLATFORM   = 'offscreen'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh '''
                    git log -1 --pretty=fuller
                    echo "commit: $(git rev-parse HEAD)"
                    echo "branch: $(git rev-parse --abbrev-ref HEAD)"
                '''
            }
        }

        stage('Setup') {
            steps {
                sh '''
                    python3 --version
                    python3 -m venv "${VENV}"
                    "${VENV}/bin/python" -m pip install --upgrade pip
                    "${VENV}/bin/python" -m pip install -r requirements.txt pytest pyinstaller
                    "${VENV}/bin/python" -m pip list
                '''
            }
        }

        stage('Check') {
            steps {
                sh 'make check PYTHON="${VENV}/bin/python"'
            }
        }

        stage('Tests') {
            steps {
                sh '''
                    if [ -d tests ]; then
                        QT_QPA_PLATFORM=offscreen make test PYTHON="${VENV}/bin/python"
                    else
                        echo "tests: no tests/ directory yet - skipping pytest"
                    fi
                '''
            }
        }

        stage('Package') {
            steps {
                script {
                    // The PyInstaller bundle is slow; build it on request or
                    // for a release, and always publish the source bundle.
                    if (params.PACKAGE || env.TAG_NAME) {
                        sh 'rm -rf dist && make package PYTHON="${VENV}/bin/python"'
                    }
                }
                sh '''
                    mkdir -p dist
                    files="flash_gui.py gui requirements.txt README.md LICENSE"
                    if [ -n "$(ls -A dist 2>/dev/null)" ]; then
                        files="$files dist"
                    fi
                    python3 ci/package.py --name bootloader-gui --version "$(ci/version.sh)" $files
                '''
            }
        }

        stage('Release') {
            // Only for a tag build (Multibranch job with tag discovery).  The
            // tag must be v<version>; ci/github_release.py checks it.
            when { buildingTag() }
            steps {
                withCredentials([string(credentialsId: 'github-release-token', variable: 'GITHUB_TOKEN')]) {
                    sh 'python3 ci/github_release.py --tag "${TAG_NAME}" --version "$(ci/version.sh)" dist/*'
                }
            }
        }

        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'dist/*', fingerprint: true
            }
        }
    }

    post {
        always {
            deleteDir()
        }
        success {
            echo 'BOOT Flasher: check, tests and package checks passed.'
        }
        failure {
            echo 'BOOT Flasher: pipeline failed - see the stage logs above.'
        }
    }
}
