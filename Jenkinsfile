pipeline {
    agent any

    stages {
        stage('1. Setup Environment & Install Dependencies') {
            steps {
                bat '''
                py -m venv venv
                call venv\\Scripts\\activate
                py -m pip install --upgrade pip
                py -m pip install -r requirements.txt
                '''
            }
        }

        stage('2. Run Automated Verification') {
            steps {
                bat '''
                call venv\\Scripts\\activate
                py -c "import app; print('App syntax check passed successfully!')"
                '''
            }
        }
    }

    post {
        success {
            echo 'Jenkins CI/CD Build & Verification Passed!'
        }
        failure {
            echo 'Pipeline failed. Check logs above.'
        }
    }
}