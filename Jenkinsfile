pipeline {
    agent any

    stages {
        stage('1. Checkout Repository') {
            steps {
                git branch: 'main', url: 'https://github.com/deept1812/project_nexus.git'
            }
        }

        stage('2. Setup Environment & Install Dependencies') {
            steps {
                bat '''
                python -m venv venv
                call venv\\Scripts\\activate
                pip install --upgrade pip
                pip install -r requirements.txt
                '''
            }
        }

        stage('3. Run Automated Tests') {
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
            echo 'Pipeline executed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check build logs.'
        }
    }
}