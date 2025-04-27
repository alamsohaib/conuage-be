from pydantic import BaseModel, UUID4, ConfigDict, Field, EmailStr
from datetime import datetime
from typing import Optional, List
from uuid import UUID

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class BaseModelWithTimestamp(BaseModel):
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class OrganizationBase(BaseModel):
    name: str
    address: Optional[str] = ""
    country: Optional[str] = ""
    state: Optional[str] = ""
    city: Optional[str] = ""
    post_code: Optional[str] = ""
    is_active: bool = True
    auto_signup_enabled: bool = False
    token_balance: float = 0.0
    monthly_token_limit: int = 1000

    model_config = ConfigDict(from_attributes=True)

class OrganizationCreate(OrganizationBase):
    primary_contact_id: Optional[UUID] = None
    default_location_id: Optional[UUID] = None

class OrganizationInDB(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    primary_contact_id: Optional[UUID] = None
    default_location_id: Optional[UUID] = None

class OrganizationPrimaryContact(BaseModel):
    """Schema for organization primary contact"""
    id: UUID
    email: str
    first_name: str
    last_name: str

class OrganizationLocation(BaseModel):
    """Schema for organization location"""
    id: UUID
    name: str

class OrganizationDetail(BaseModel):
    """Schema for detailed organization view"""
    id: UUID
    name: str
    address: Optional[str]
    country: Optional[str]
    state: Optional[str]
    city: Optional[str]
    post_code: Optional[str]
    is_active: bool
    auto_signup_enabled: bool
    monthly_token_limit: Optional[int]
    primary_contact: Optional[OrganizationPrimaryContact]
    default_location: Optional[OrganizationLocation]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    chat_tokens_used: Optional[int]
    document_processing_tokens_used: Optional[int]

class OrganizationUpdate(BaseModel):
    """Schema for organization update. All fields are optional to allow partial updates."""
    address: Optional[str] = None
    state: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    post_code: Optional[str] = Field(None, max_length=20)
    auto_signup_enabled: Optional[bool] = None
    primary_contact_email: Optional[str] = None
    default_location_id: Optional[UUID] = None

    class Config:
        """Pydantic model configuration"""
        json_schema_extra = {
            "example": {
                "address": "123 Business St",
                "state": "CA",
                "city": "San Francisco",
                "post_code": "94105",
                "auto_signup_enabled": True,
                "primary_contact_email": "admin@acme.com",
                "default_location_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }

class LocationBase(BaseModel):
    name: str
    details: Optional[str] = None
    organization_id: UUID

    model_config = ConfigDict(from_attributes=True)

class LocationCreate(LocationBase):
    pass

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class Location(LocationBase, BaseModelWithTimestamp):
    id: UUID

class UserSignUp(BaseModel):
    """Schema for user signup"""
    email: EmailStr
    password: str
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)

class VerifyEmail(BaseModel):
    email: EmailStr
    code: str

    model_config = ConfigDict(from_attributes=True)

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    organization_id: UUID
    location_id: UUID
    role: str = "end_user"
    email_verified: bool = False
    status: str = "pending"

    model_config = ConfigDict(from_attributes=True)

class UserCreate(UserBase):
    password_hash: str

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class User(UserBase, BaseModelWithTimestamp):
    id: UUID
    last_login: Optional[datetime] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    role: Optional[str] = None

class UserBase(BaseModel):
    organization_id: Optional[UUID] = None
    email: Optional[str] = ""
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    email_verified: bool = False
    status: str = "active"
    status_changed_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status_changed_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)

class UserCreate(UserBase):
    pass

class UserInDB(UserBase):
    id: UUID
    created_at: datetime

class UserLocationBase(BaseModel):
    location_id: UUID
    is_primary: bool = False

class UserLocationCreate(UserLocationBase):
    pass

class UserLocationUpdate(UserLocationBase):
    pass

class UserLocationResponse(UserLocationBase):
    """Response model for user location"""
    id: UUID
    location_id: UUID
    location_name: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime

class UserManagementCreate(BaseModel):
    """Schema for creating a new user by org admin"""
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    location_id: UUID  # Primary location
    additional_location_ids: List[UUID] = []  # Additional locations
    role: str = "end_user"
    status: str = "active"

    model_config = ConfigDict(from_attributes=True)

class UserManagementUpdate(BaseModel):
    """Schema for updating user details by org admin"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    location_id: Optional[UUID] = None  # Primary location
    additional_location_ids: Optional[List[UUID]] = None  # Additional locations
    role: Optional[str] = None
    status: Optional[str] = None

class UserResponse(BaseModel):
    """Schema for user response"""
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    organization_id: UUID
    locations: List[UserLocationResponse]
    role: str
    email_verified: bool
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DocumentBase(BaseModel):
    """Base schema for document operations"""
    name: str
    folder_id: UUID
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    page_count: Optional[int] = 0
    status: str = "added"

    model_config = ConfigDict(from_attributes=True)

class DocumentCreate(DocumentBase):
    """Schema for creating a document"""
    pass

class DocumentUpdate(BaseModel):
    """Schema for updating a document"""
    name: Optional[str] = None
    folder_id: Optional[UUID] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    page_count: Optional[int] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class Document(DocumentBase):
    """Schema for document response"""
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID

    model_config = ConfigDict(from_attributes=True)

class FolderBase(BaseModel):
    """Base schema for folder operations"""
    name: str
    location_id: UUID
    parent_folder_id: Optional[UUID] = None

class FolderCreate(FolderBase):
    """Schema for creating a folder"""
    pass

class FolderUpdate(BaseModel):
    """Schema for updating a folder"""
    name: str

class Folder(FolderBase):
    """Schema for folder response"""
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID

class FolderWithChildren(Folder):
    """Folder model with children for hierarchical structure"""
    children: List["FolderWithChildren"] = []

FolderWithChildren.update_forward_refs()

class DocumentEmbedding(BaseModel):
    """Schema for document embeddings"""
    id: Optional[UUID] = None
    document_id: UUID
    location_id: UUID
    page_number: int
    content: str
    embedding: List[float]  # Keep as List[float] for proper vector handling
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            list: lambda v: list(v)  # Ensure lists are properly serialized
        }

class DocumentProcessResponse(BaseModel):
    """Response schema for document processing"""
    message: str
    document_id: UUID
    total_pages_processed: int

class DeleteResponse(BaseModel):
    """Response model for delete operations"""
    message: str
    id: UUID

class DocumentDeleteResponse(DeleteResponse):
    """Response model for document deletion"""
    file_path: str
    folder_id: UUID

class FolderDeleteResponse(DeleteResponse):
    """Response model for folder deletion"""
    location_id: UUID
    documents_deleted: int
    subfolders_deleted: int

class ChatCreate(BaseModel):
    """Schema for creating a new chat"""
    name: str

class Chat(ChatCreate):
    """Schema for chat response"""
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

class MessageCreate(BaseModel):
    """Schema for creating a new message"""
    content: str

class MessageSource(BaseModel):
    """Schema for message source"""
    document_id: UUID
    page_number: int
    content: str
    content_type: str
    similarity_score: float
    document_name: str | None = None
    file_path: str | None = None

class Message(BaseModel):
    """Schema for message response"""
    id: UUID
    chat_id: UUID
    content: str
    role: str
    created_at: datetime
    sources: List[MessageSource] | None = None

class ChatResponse(BaseModel):
    """Schema for chat with messages"""
    chat: Chat
    messages: List[Message]

class ChatListResponse(BaseModel):
    """Schema for list of chats"""
    chats: List[Chat]

class StreamingMessageResponse(BaseModel):
    """Streaming message response"""
    content: str
    role: str = "assistant"
    delta: bool = True
    sources: List[MessageSource] | None = None

class ForgotPassword(BaseModel):
    """Schema for forgot password request"""
    email: EmailStr

class ResetPassword(BaseModel):
    """Schema for password reset request"""
    code: str
    new_password: str = Field(..., min_length=8)

class ChangePassword(BaseModel):
    """Schema for password change request"""
    current_password: str
    new_password: str = Field(..., min_length=8)

class UserLocation(BaseModel):
    """Schema for user location access"""
    location_id: UUID
    location_name: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime

class UserProfile(BaseModel):
    """Schema for user profile"""
    id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    status: str
    email_verified: bool
    last_login: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    chat_tokens_used: Optional[int]
    document_processing_tokens_used: Optional[int]
    daily_chat_tokens_used: int
    daily_document_processing_tokens_used: int
    daily_token_limit: int
    profile_photo_url: Optional[str]
    locations: List[UserLocation]

class UpdateProfile(BaseModel):
    """Schema for profile update"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)

class PricingPlanBase(BaseModel):
    """Base schema for pricing plans"""
    name: str
    cost: float
    monthly_token_limit_per_user: int
    daily_token_limit_per_user: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

class PricingPlan(PricingPlanBase):
    """Schema for pricing plan response"""
    id: UUID
    created_at: datetime
    updated_at: datetime

class PricingPlanSubscription(BaseModel):
    """Schema for updating organization's pricing plan subscription"""
    pricing_plan_id: UUID
    number_of_users_paid: int = Field(..., gt=0, description="Number of user licenses to purchase")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "pricing_plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "number_of_users_paid": 5
            }
        }
    )

class PricingPlanSubscriptionResponse(BaseModel):
    """Response schema for pricing plan subscription"""
    organization_id: UUID
    pricing_plan: PricingPlan
    number_of_users_paid: int
    subscription_start_date: datetime
    subscription_end_date: Optional[datetime]
    monthly_cost: float

    model_config = ConfigDict(from_attributes=True)
