#!/usr/bin/env python3
"""
KNOWLEDGEBASE INGEST SYSTEM
============================

Sistema avanzato di elaborazione documenti con:
- Supporto multi-formato (PDF, DOCX, TXT, HTML, MD)
- Chunking intelligente
- Embeddings GPU/CPU
- Processing incrementale
- Metadata extraction
- Error handling e retry logic
- Progress monitoring

Autore: vcapoccia
Versione: 2.0.0
"""

import asyncio
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict
from contextlib import contextmanager

# Core libraries
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from qdrant_client.http.exceptions import ResponseHandlingException

# Document processing
from processors import (
    PDFProcessor, 
    DOCXProcessor, 
    TextProcessor, 
    HTMLProcessor,
    MarkdownProcessor
)
from embeddings import EmbeddingGenerator
from utils import setup_logging, get_file_hash, chunk_text_intelligent

# Progress tracking
from tqdm import tqdm
import psutil

# =======================================================================
# CONFIGURATION AND MODELS
# =======================================================================

@dataclass
class IngestConfig:
    """Configuration for ingest process"""
    # Paths
    kb_root: str = "/home/vcapoccia/knowledgebase/docs"
    temp_dir: str = "/app/temp"
    models_dir: str = "/app/models"
    cache_dir: str = "/app/cache"
    
    # Qdrant settings
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "kb_chunks"
    vector_size: int = 384
    
    # Processing settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"  # or "cuda"
    batch_size: int = 100
    max_chunk_size: int = 1000
    chunk_overlap: int = 200
    max_workers: int = 4
    
    # File settings
    supported_extensions: List[str] = None
    max_file_size_mb: int = 100
    
    # Processing flags
    incremental: bool = True
    force_reingest: bool = False
    dry_run: bool = False
    watch_mode: bool = False
    
    def __post_init__(self):
        if self.supported_extensions is None:
            self.supported_extensions = ['.pdf', '.docx', '.txt', '.html', '.md']

@dataclass
class DocumentMetadata:
    """Document metadata structure"""
    file_path: str
    file_name: str
    file_size: int
    file_hash: str
    file_type: str
    category: str
    title: Optional[str] = None
    author: Optional[str] = None
    creation_date: Optional[datetime] = None
    modification_date: Optional[datetime] = None
    language: Optional[str] = None
    tags: List[str] = None
    extracted_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()

@dataclass
class DocumentChunk:
    """Document chunk with embeddings"""
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    metadata: DocumentMetadata
    embedding: Optional[np.ndarray] = None
    
    def to_point(self) -> PointStruct:
        """Convert to Qdrant point"""
        if self.embedding is None:
            raise ValueError("Embedding not generated")
            
        payload = {
            "text": self.text,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "file_path": self.metadata.file_path,
            "file_name": self.metadata.file_name,
            "file_type": self.metadata.file_type,
            "category": self.metadata.category,
            "title": self.metadata.title,
            "author": self.metadata.author,
            "creation_date": self.metadata.creation_date.isoformat() if self.metadata.creation_date else None,
            "modification_date": self.metadata.modification_date.isoformat() if self.metadata.modification_date else None,
            "language": self.metadata.language,
            "tags": self.metadata.tags,
            "extracted_at": self.metadata.extracted_at.isoformat(),
        }
        
        return PointStruct(
            id=self.chunk_id,
            vector=self.embedding.tolist(),
            payload=payload
        )

# =======================================================================
# MAIN INGEST CLASS
# =======================================================================

class KnowledgeBaseIngest:
    """Main ingest system for knowledge base documents"""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        self.logger = self._setup_logging()
        
        # Initialize components
        self.qdrant_client = None
        self.embedding_generator = None
        self.processors = {}
        
        # Statistics
        self.stats = {
            'processed_files': 0,
            'skipped_files': 0,
            'failed_files': 0,
            'total_chunks': 0,
            'processing_time': 0,
            'start_time': None
        }
        
        # Progress tracking
        self.progress_bar = None
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = setup_logging(
            name="kb_ingest",
            level=logging.DEBUG if self.config.dry_run else logging.INFO,
            log_file=Path(self.config.temp_dir) / "ingest.log"
        )
        return logger
    
    async def initialize(self):
        """Initialize all components"""
        self.logger.info("🚀 Initializing Knowledge Base Ingest System v2.0")
        
        try:
            # Create directories
            for dir_path in [self.config.temp_dir, self.config.models_dir, self.config.cache_dir]:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            
            # Initialize Qdrant
            await self._initialize_qdrant()
            
            # Initialize embedding generator
            await self._initialize_embeddings()
            
            # Initialize document processors
            self._initialize_processors()
            
            # Log system info
            self._log_system_info()
            
            self.logger.info("✅ Initialization completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {str(e)}")
            raise
    
    async def _initialize_qdrant(self):
        """Initialize Qdrant client and collection"""
        self.logger.info("🔌 Connecting to Qdrant...")
        
        self.qdrant_client = QdrantClient(url=self.config.qdrant_url)
        
        # Test connection
        try:
            collections = self.qdrant_client.get_collections()
            self.logger.info(f"✅ Connected to Qdrant. Collections: {len(collections.collections)}")
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Qdrant: {str(e)}")
            raise
        
        # Create collection if not exists
        await self._ensure_collection_exists()
    
    async def _ensure_collection_exists(self):
        """Ensure the collection exists with correct configuration"""
        collections = self.qdrant_client.get_collections()
        collection_names = [col.name for col in collections.collections]
        
        if self.config.qdrant_collection not in collection_names:
            self.logger.info(f"📁 Creating collection: {self.config.qdrant_collection}")
            
            self.qdrant_client.create_collection(
                collection_name=self.config.qdrant_collection,
                vectors_config=VectorParams(
                    size=self.config.vector_size,
                    distance=Distance.COSINE
                )
            )
            self.logger.info("✅ Collection created successfully")
        else:
            # Verify collection configuration
            collection_info = self.qdrant_client.get_collection(self.config.qdrant_collection)
            if collection_info.config.params.vectors.size != self.config.vector_size:
                self.logger.warning("⚠️  Collection vector size mismatch")
    
    async def _initialize_embeddings(self):
        """Initialize embedding generator"""
        self.logger.info(f"🧠 Loading embedding model: {self.config.embedding_model}")
        
        # Check device availability
        if self.config.device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("⚠️  CUDA requested but not available, falling back to CPU")
            self.config.device = "cpu"
        
        self.embedding_generator = EmbeddingGenerator(
            model_name=self.config.embedding_model,
            device=self.config.device,
            cache_dir=self.config.cache_dir
        )
        
        await self.embedding_generator.initialize()
        self.logger.info(f"✅ Embedding model loaded on {self.config.device}")
    
    def _initialize_processors(self):
        """Initialize document processors"""
        self.logger.info("📄 Initializing document processors...")
        
        self.processors = {
            '.pdf': PDFProcessor(),
            '.docx': DOCXProcessor(),
            '.txt': TextProcessor(),
            '.html': HTMLProcessor(),
            '.md': MarkdownProcessor(),
        }
        
        # Initialize each processor
        for ext, processor in self.processors.items():
            try:
                processor.initialize()
                self.logger.info(f"✅ {ext.upper()} processor ready")
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {ext} processor: {str(e)}")
    
    def _log_system_info(self):
        """Log system information"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(self.config.kb_root)
        
        self.logger.info("💻 System Information:")
        self.logger.info(f"   Memory: {memory.used // 1024**3}GB / {memory.total // 1024**3}GB ({memory.percent}%)")
        self.logger.info(f"   Disk: {disk.used // 1024**3}GB / {disk.total // 1024**3}GB ({disk.percent}%)")
        self.logger.info(f"   CPU Count: {psutil.cpu_count()}")
        self.logger.info(f"   CUDA Available: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            self.logger.info(f"   GPU: {torch.cuda.get_device_name()}")
            self.logger.info(f"   GPU Memory: {torch.cuda.get_device_properties(0).total_memory // 1024**3}GB")
    
    # =======================================================================
    # MAIN PROCESSING METHODS
    # =======================================================================
    
    async def run(self):
        """Main ingest process"""
        self.logger.info("🔄 Starting document ingestion process")
        self.stats['start_time'] = time.time()
        
        try:
            # Discover files to process
            files_to_process = await self._discover_files()
            
            if not files_to_process:
                self.logger.info("ℹ️  No files to process")
                return
            
            self.logger.info(f"📊 Found {len(files_to_process)} files to process")
            
            # Process files
            if self.config.dry_run:
                self.logger.info("🧪 DRY RUN MODE - No actual processing")
                await self._dry_run_process(files_to_process)
            else:
                await self._process_files(files_to_process)
            
            # Show final statistics
            self._show_final_stats()
            
        except KeyboardInterrupt:
            self.logger.info("⏹️  Processing interrupted by user")
        except Exception as e:
            self.logger.error(f"❌ Processing failed: {str(e)}")
            raise
        finally:
            if self.progress_bar:
                self.progress_bar.close()
    
    async def _discover_files(self) -> List[Path]:
        """Discover files that need processing"""
        self.logger.info("🔍 Discovering files...")
        
        all_files = []
        kb_root = Path(self.config.kb_root)
        
        if not kb_root.exists():
            self.logger.error(f"❌ KB root directory not found: {kb_root}")
            return []
        
        # Collect all supported files
        for ext in self.config.supported_extensions:
            pattern = f"**/*{ext}"
            files = list(kb_root.glob(pattern))
            all_files.extend(files)
            self.logger.debug(f"Found {len(files)} {ext.upper()} files")
        
        self.logger.info(f"📁 Total files found: {len(all_files)}")
        
        # Filter files that need processing
        if self.config.incremental and not self.config.force_reingest:
            files_to_process = await self._filter_files_for_incremental(all_files)
        else:
            files_to_process = all_files
        
        # Filter by file size
        files_to_process = self._filter_by_size(files_to_process)
        
        return sorted(files_to_process)
    
    async def _filter_files_for_incremental(self, files: List[Path]) -> List[Path]:
        """Filter files for incremental processing"""
        self.logger.info("🔄 Filtering for incremental processing...")
        
        files_to_process = []
        
        for file_path in files:
            try:
                # Get file hash
                file_hash = get_file_hash(file_path)
                
                # Check if already processed
                existing_points = self.qdrant_client.scroll(
                    collection_name=self.config.qdrant_collection,
                    scroll_filter={
                        "must": [
                            {"key": "file_path", "match": {"value": str(file_path)}},
                            {"key": "file_hash", "match": {"value": file_hash}}
                        ]
                    },
                    limit=1
                )
                
                if not existing_points[0]:  # No existing points found
                    files_to_process.append(file_path)
                    self.logger.debug(f"📄 New/modified file: {file_path.name}")
                else:
                    self.logger.debug(f"⏭️  Skipping unchanged file: {file_path.name}")
                    self.stats['skipped_files'] += 1
                    
            except Exception as e:
                self.logger.warning(f"⚠️  Error checking file {file_path}: {str(e)}")
                files_to_process.append(file_path)  # Include if uncertain
        
        self.logger.info(f"🔄 Files to process after incremental filter: {len(files_to_process)}")
        return files_to_process
    
    def _filter_by_size(self, files: List[Path]) -> List[Path]:
        """Filter files by maximum size"""
        max_size = self.config.max_file_size_mb * 1024 * 1024
        filtered_files = []
        
        for file_path in files:
            try:
                if file_path.stat().st_size <= max_size:
                    filtered_files.append(file_path)
                else:
                    self.logger.warning(f"⚠️  File too large, skipping: {file_path.name}")
                    self.stats['skipped_files'] += 1
            except Exception as e:
                self.logger.warning(f"⚠️  Error checking file size {file_path}: {str(e)}")
        
        return filtered_files
    
    async def _dry_run_process(self, files: List[Path]):
        """Dry run process - shows what would be done"""
        self.logger.info("🧪 DRY RUN - Analysis of files to be processed:")
        
        file_stats = {}
        total_size = 0
        
        for file_path in files:
            try:
                stat = file_path.stat()
                file_type = file_path.suffix.lower()
                
                if file_type not in file_stats:
                    file_stats[file_type] = {'count': 0, 'size': 0}
                
                file_stats[file_type]['count'] += 1
                file_stats[file_type]['size'] += stat.st_size
                total_size += stat.st_size
                
            except Exception as e:
                self.logger.warning(f"⚠️  Error analyzing file {file_path}: {str(e)}")
        
        # Show statistics
        self.logger.info(f"📊 DRY RUN Results:")
        self.logger.info(f"   Total files: {len(files)}")
        self.logger.info(f"   Total size: {total_size / 1024**2:.1f} MB")
        
        for file_type, stats in file_stats.items():
            self.logger.info(f"   {file_type.upper()}: {stats['count']} files, {stats['size'] / 1024**2:.1f} MB")
    
    async def _process_files(self, files: List[Path]):
        """Process all files with parallel processing"""
        self.logger.info(f"⚙️  Processing {len(files)} files with {self.config.max_workers} workers...")
        
        # Initialize progress bar
        self.progress_bar = tqdm(
            total=len(files),
            desc="Processing files",
            unit="file",
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {rate_fmt}'
        )
        
        # Process files in batches to manage memory
        batch_size = self.config.max_workers * 2
        
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            await self._process_batch(batch)
            
            # Memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    
    async def _process_batch(self, batch: List[Path]):
        """Process a batch of files"""
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Submit all files in batch
            future_to_file = {
                executor.submit(self._process_single_file, file_path): file_path
                for file_path in batch
            }
            
            # Process completed futures
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    if result:
                        self.stats['processed_files'] += 1
                        self.stats['total_chunks'] += result.get('chunks', 0)
                    else:
                        self.stats['failed_files'] += 1
                        
                except Exception as e:
                    self.logger.error(f"❌ Error processing {file_path}: {str(e)}")
                    self.stats['failed_files'] += 1
                
                finally:
                    self.progress_bar.update(1)
    
    def _process_single_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Process a single file"""
        try:
            start_time = time.time()
            
            # Extract metadata
            metadata = self._extract_metadata(file_path)
            
            # Choose processor
            processor = self.processors.get(file_path.suffix.lower())
            if not processor:
                self.logger.warning(f"⚠️  No processor for file type: {file_path.suffix}")
                return None
            
            # Extract text
            text = processor.extract_text(file_path)
            if not text or len(text.strip()) < 50:
                self.logger.warning(f"⚠️  No meaningful text extracted from: {file_path.name}")
                return None
            
            # Chunk text
            chunks = chunk_text_intelligent(
                text,
                max_chunk_size=self.config.max_chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )
            
            # Create document chunks
            document_chunks = []
            document_id = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
            
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{document_id}_{i:04d}"
                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=chunk_text,
                    chunk_index=i,
                    metadata=metadata
                )
                document_chunks.append(chunk)
            
            # Generate embeddings
            self._generate_embeddings(document_chunks)
            
            # Store in Qdrant
            points = [chunk.to_point() for chunk in document_chunks]
            
            # Remove existing points for this document (for updates)
            self.qdrant_client.delete(
                collection_name=self.config.qdrant_collection,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "file_path", "match": {"value": str(file_path)}}
                        ]
                    }
                }
            )
            
            # Insert new points
            self.qdrant_client.upsert(
                collection_name=self.config.qdrant_collection,
                points=points
            )
            
            processing_time = time.time() - start_time
            
            self.logger.debug(f"✅ Processed {file_path.name}: {len(chunks)} chunks in {processing_time:.2f}s")
            
            return {
                'file_path': str(file_path),
                'chunks': len(chunks),
                'processing_time': processing_time
            }
            
        except Exception as e:
            self.logger.error(f"❌ Failed to process {file_path}: {str(e)}")
            return None
    
    def _extract_metadata(self, file_path: Path) -> DocumentMetadata:
        """Extract metadata from file"""
        stat = file_path.stat()
        file_hash = get_file_hash(file_path)
        
        # Determine category
        category = "general"
        if "_Gare" in str(file_path):
            category = "gare"
        elif "_AQ" in str(file_path):
            category = "aq"
        
        # Extract additional metadata using processor
        additional_metadata = {}
        processor = self.processors.get(file_path.suffix.lower())
        if processor and hasattr(processor, 'extract_metadata'):
            try:
                additional_metadata = processor.extract_metadata(file_path)
            except Exception as e:
                self.logger.debug(f"Failed to extract additional metadata from {file_path}: {str(e)}")
        
        return DocumentMetadata(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size=stat.st_size,
            file_hash=file_hash,
            file_type=file_path.suffix.lower(),
            category=category,
            title=additional_metadata.get('title', file_path.stem),
            author=additional_metadata.get('author'),
            creation_date=additional_metadata.get('creation_date'),
            modification_date=datetime.fromtimestamp(stat.st_mtime),
            language=additional_metadata.get('language'),
            tags=additional_metadata.get('tags', [])
        )
    
    def _generate_embeddings(self, chunks: List[DocumentChunk]):
        """Generate embeddings for chunks"""
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_generator.generate_batch(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
    
    def _show_final_stats(self):
        """Show final processing statistics"""
        processing_time = time.time() - self.stats['start_time']
        
        self.logger.info("📊 Final Processing Statistics:")
        self.logger.info(f"   ✅ Processed files: {self.stats['processed_files']}")
        self.logger.info(f"   ⏭️  Skipped files: {self.stats['skipped_files']}")
        self.logger.info(f"   ❌ Failed files: {self.stats['failed_files']}")
        self.logger.info(f"   📄 Total chunks: {self.stats['total_chunks']}")
        self.logger.info(f"   ⏱️  Total time: {processing_time:.2f}s")
        
        if self.stats['processed_files'] > 0:
            avg_time = processing_time / self.stats['processed_files']
            self.logger.info(f"   📈 Average time per file: {avg_time:.2f}s")
    
    async def cleanup(self):
        """Cleanup resources"""
        self.logger.info("🧹 Cleaning up resources...")
        
        if self.embedding_generator:
            await self.embedding_generator.cleanup()
        
        if self.qdrant_client:
            self.qdrant_client.close()
        
        self.logger.info("✅ Cleanup completed")


# =======================================================================
# CLI INTERFACE
# =======================================================================

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Knowledge Base Document Ingest System v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python ingest.py                          # Standard incremental ingest
    python ingest.py --force-reingest         # Force reprocess all files
    python ingest.py --dry-run                # Preview what would be processed
    python ingest.py --device cuda            # Use GPU for embeddings
    python ingest.py --batch-size 200         # Larger batch size
    python ingest.py --watch                  # Watch mode for development
        """
    )
    
    # Paths
    parser.add_argument('--kb-root', default=os.getenv('KB_ROOT', '/home/vcapoccia/knowledgebase/docs'),
                       help='Knowledge base root directory')
    parser.add_argument('--temp-dir', default='/app/temp',
                       help='Temporary directory')
    
    # Qdrant settings
    parser.add_argument('--qdrant-url', default=os.getenv('QDRANT_URL', 'http://qdrant:6333'),
                       help='Qdrant server URL')
    parser.add_argument('--qdrant-collection', default=os.getenv('QDRANT_COLLECTION', 'kb_chunks'),
                       help='Qdrant collection name')
    
    # Processing settings
    parser.add_argument('--embedding-model', default=os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'),
                       help='Embedding model name')
    parser.add_argument('--device', default=os.getenv('TORCH_DEVICE', 'cpu'),
                       choices=['cpu', 'cuda'], help='Device for embeddings')
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('BATCH_SIZE', '100')),
                       help='Processing batch size')
    parser.add_argument('--max-chunk-size', type=int, default=int(os.getenv('MAX_CHUNK_SIZE', '1000')),
                       help='Maximum chunk size in characters')
    parser.add_argument('--chunk-overlap', type=int, default=int(os.getenv('CHUNK_OVERLAP', '200')),
                       help='Overlap between chunks')
    parser.add_argument('--max-workers', type=int, default=int(os.getenv('MAX_WORKERS', '4')),
                       help='Maximum worker threads')
    
    # Processing modes
    parser.add_argument('--incremental', action='store_true', default=True,
                       help='Incremental processing (default)')
    parser.add_argument('--force-reingest', action='store_true',
                       help='Force reprocess all files')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview what would be processed')
    parser.add_argument('--watch', action='store_true',
                       help='Watch for file changes (development)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    return parser.parse_args()


# =======================================================================
# MAIN ENTRY POINT
# =======================================================================

async def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Create configuration
    config = IngestConfig(
        kb_root=args.kb_root,
        temp_dir=args.temp_dir,
        qdrant_url=args.qdrant_url,
        qdrant_collection=args.qdrant_collection,
        embedding_model=args.embedding_model,
        device=args.device,
        batch_size=args.batch_size,
        max_chunk_size=args.max_chunk_size,
        chunk_overlap=args.chunk_overlap,
        max_workers=args.max_workers,
        incremental=args.incremental and not args.force_reingest,
        force_reingest=args.force_reingest,
        dry_run=args.dry_run,
        watch_mode=args.watch
    )
    
    # Create ingest system
    ingest_system = KnowledgeBaseIngest(config)
    
    try:
        # Initialize
        await ingest_system.initialize()
        
        # Run processing
        if args.watch:
            # Watch mode for development
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            
            class IngestEventHandler(FileSystemEventHandler):
                def __init__(self, ingest_system):
                    self.ingest_system = ingest_system
                    
                def on_modified(self, event):
                    if not event.is_directory:
                        asyncio.create_task(ingest_system.run())
            
            observer = Observer()
            observer.schedule(IngestEventHandler(ingest_system), config.kb_root, recursive=True)
            observer.start()
            
            print("👀 Watching for file changes... Press Ctrl+C to stop")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()
        else:
            # One-time processing
            await ingest_system.run()
            
    except KeyboardInterrupt:
        print("\n⏹️  Process interrupted by user")
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
    finally:
        await ingest_system.cleanup()


if __name__ == "__main__":
    # Run main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"💥 Fatal error: {str(e)}")
        sys.exit(1)