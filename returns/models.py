from django.db import models


class Return(models.Model):
    # Business Rule (Returns & Refunds): 'Refund never automatic — requires
    # physical admin review first' — every return starts here, never
    # auto-approved. APPROVED/REJECTED are set by US-26 (admin review), not
    # by this story.
    STATUS_PENDING_REVIEW = 'PENDING_REVIEW'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING_REVIEW, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    order_item = models.ForeignKey(
        'orders.OrderItem', on_delete=models.PROTECT,
        related_name='return_requests')
    quantity = models.PositiveSmallIntegerField()
    reason = models.TextField()
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING_REVIEW)
    requested_at = models.DateTimeField(auto_now_add=True)
    # US-17: the admin's reason for rejecting — required on reject, matches
    # US-26's "approve or reject the return with a reason". Blank on
    # approval and while still pending.
    resolution_reason = models.CharField(max_length=255, blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['-requested_at']),
        ]
