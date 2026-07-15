import io
import os
from typing import List, Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

def get_gdrive_service(credentials_info: Dict[str, Any]):
    """Authenticates with Google Drive API using Service Account credentials JSON."""
    try:
        creds = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        raise RuntimeError(f"Google Drive API 인증 실패: {str(e)}")

def list_files_in_folder(service, folder_id: str) -> List[Dict[str, Any]]:
    """Recursively lists all files in a specific Google Drive folder.
    Returns a list of dicts with file metadata.
    """
    try:
        files = []
        
        # Helper inner function for recursive listing
        def _list_recursive(current_folder_id: str, relative_path: str = ""):
            query = f"'{current_folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)"
            ).execute()
            
            items = results.get('files', [])
            for item in items:
                name = item['name']
                mime_type = item['mimeType']
                file_id = item['id']
                mod_time = item['modifiedTime']
                
                # Check if it's a sub-directory
                if mime_type == 'application/vnd.google-apps.folder':
                    sub_path = os.path.join(relative_path, name).replace("\\", "/")
                    _list_recursive(file_id, sub_path)
                else:
                    # Clean/normalize paths for storage
                    rel_file_path = os.path.join(relative_path, name).replace("\\", "/")
                    files.append({
                        "id": file_id,
                        "name": name,
                        "rel_path": rel_file_path,
                        "mimeType": mime_type,
                        "modifiedTime": mod_time
                    })
                    
        _list_recursive(folder_id)
        return files
    except Exception as e:
        raise RuntimeError(f"구글 드라이브 파일 목록 검색 실패: {str(e)}")

def download_file(service, file_info: Dict[str, Any], dest_path: str) -> str:
    """Downloads a file from Google Drive.
    If the file is a Google Workspace native format (Doc/Sheet), exports it to .docx/.xlsx.
    Returns the final local file path (which might have changed extension).
    """
    file_id = file_info['id']
    mime_type = file_info['mimeType']
    final_path = dest_path
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    try:
        # Handle Google Workspace documents by exporting them to standard Microsoft formats
        if mime_type == 'application/vnd.google-apps.document':
            # Export Google Doc to Word .docx
            request = service.files().export_media(
                fileId=file_id, 
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            if not final_path.endswith('.docx'):
                final_path += '.docx'
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            # Export Google Sheet to Excel .xlsx
            request = service.files().export_media(
                fileId=file_id, 
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            if not final_path.endswith('.xlsx'):
                final_path += '.xlsx'
        else:
            # Download binary/standard file media directly (PDF, docx, xlsx, hwpx, txt, etc.)
            request = service.files().get_media(fileId=file_id)
            
        # Write down the file streams
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        with open(final_path, 'wb') as f:
            f.write(fh.getvalue())
            
        return final_path
    except Exception as e:
        raise RuntimeError(f"파일 다운로드 실패 ({file_info['name']}): {str(e)}")
