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

        stage('3. Trigger Render Auto-Deploy') {
            steps {
                bat 'curl -X POST https://api.render.com/deploy/srv-dbn0vajm8hqs73bkrbf0?key=k0nNbYPAVJo'
            }
        }
    }

    post {
        success {
            echo 'Jenkins CI/CD Pipeline Passed! Deployment trigger successfully sent to Render.'
        }
        failure {
            echo 'Pipeline failed. Deployment skipped.'
        }
    }
}