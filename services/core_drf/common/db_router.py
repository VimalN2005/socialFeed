import os
import random
import logging
from typing import Optional, Type
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)

class PrimaryReplicaRouter:
    """
    Production Database Router for High-Throughput Read-Replica Splitting.
    
    Routing Strategy:
    - Writes (INSERT, UPDATE, DELETE): Always directed to 'default' (Primary / Leader DB).
    - Reads (SELECT): Load-balanced across active read-replicas ('replica', 'replica_1', etc.).
      Falls back to 'default' if no replicas are configured.
    - Schema Migrations: Strictly executed on 'default' only.
    - Relations: Permitted across replicas and default as they share the same schema.
    """

    def _get_read_replicas(self) -> list:
        """Find all configured replica databases in settings.DATABASES."""
        databases = getattr(settings, 'DATABASES', {})
        replicas = [db for db in databases if db.startswith('replica')]
        return replicas

    def db_for_read(self, model: Type[models.Model], **hints) -> str:
        """
        Route read operations to available read replicas.
        If multiple replicas exist, randomly select one for distributed load balancing.
        """
        replicas = self._get_read_replicas()
        if replicas:
            chosen = random.choice(replicas)
            return chosen
        return 'default'

    def db_for_write(self, model: Type[models.Model], **hints) -> str:
        """
        Route all write operations strictly to the Primary (default) database.
        """
        return 'default'

    def allow_relation(self, obj1: models.Model, obj2: models.Model, **hints) -> bool:
        """
        Allow any relation between objects if they are in the primary-replica cluster.
        """
        db_set = {'default'}
        db_set.update(self._get_read_replicas())
        if obj1._state.db in db_set and obj2._state.db in db_set:
            return True
        return None

    def allow_migrate(self, db: str, app_label: str, model_name: Optional[str] = None, **hints) -> bool:
        """
        Ensure all schema migrations run strictly on the 'default' primary database.
        Replicas sync via PostgreSQL WAL streaming replication.
        """
        return db == 'default'
