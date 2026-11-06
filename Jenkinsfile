pipeline {
    agent any

    stages {
        stage('1. Setup Environment & Install Dependencies') {
            steps {
                bat '''
                python -m venv venv || py -m venv venv || "C:\\Users\\User\\OneDrive\\Desktop\\Project_Nexus\\venv\\Scripts\\python.exe" -m venv venv
                call venv\\Scripts\\activate
                python -m pip install --upgrade pip
                python -m pip install -r requirements.txt
                '''
            }
        }

        stage('2. Run Automated Verification') {
            steps {
                bat '''
                call venv\\Scripts\\activate
                python -c "import app; print('App syntax check passed successfully!')"
                '''
            }
        }
    }

    post {
        success {
            echo 'Jenkins CI/CD Build & Verification Passed!'
        }
        failure {
            echo 'Pipeline failed. Check build logs above.'
        }
    }
}