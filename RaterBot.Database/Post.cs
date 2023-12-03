// ---------------------------------------------------------------------------------------------------
// <auto-generated>
// This code was generated by LinqToDB scaffolding tool (https://github.com/linq2db/linq2db).
// Changes to this file may cause incorrect behavior and will be lost if the code is regenerated.
// </auto-generated>
// ---------------------------------------------------------------------------------------------------

using LinqToDB.Mapping;
using System;
using System.Collections.Generic;

#pragma warning disable 1573, 1591
#nullable enable

namespace RaterBot.Database
{
	[Table("Post")]
	public class Post
	{
		[Column("Id"            , IsPrimaryKey = true, IsIdentity = true, SkipOnInsert = true, SkipOnUpdate = true)] public long     Id             { get; set; } // integer
		[Column("ChatId"                                                                                          )] public long     ChatId         { get; set; } // integer
		[Column("PosterId"                                                                                        )] public long     PosterId       { get; set; } // integer
		[Column("MessageId"                                                                                       )] public long     MessageId      { get; set; } // integer
		[Column("Timestamp"                                                                                       )] public DateTime Timestamp      { get; set; } // datetime
		[Column("ReplyMessageId"                                                                                  )] public long?    ReplyMessageId { get; set; } // integer

		#region Associations
		/// <summary>
		/// FK_Interaction_0_0 backreference
		/// </summary>
		[Association(ThisKey = nameof(Id), OtherKey = nameof(Interaction.PostId))]
		public IEnumerable<Interaction> Interactions { get; set; } = null!;
		#endregion
	}
}
